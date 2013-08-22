from gi.repository import GObject
import logging
import socket
import threading
import Queue
import weakref
import select
import re
import multiprocessing
import select
import modbus_tk.modbus_tcp
import modbus_tk.defines
import os
import time
from ...utils import objwithgui

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class InstrumentError(StandardError):
    pass

class ConnectionBrokenError(InstrumentError):
    pass

class InstrumentTimeoutError(InstrumentError):
    pass

class InstrumentStatus(object):
    Disconnected = 'disconnected'
    Idle = 'idle'
    Busy = 'busy'

class InstrumentPropertyCategory(object):
    UNKNOWN = 'Unknown'
    ERROR = 'Error'
    WARNING = 'Warning'
    NORMAL = 'Normal'
    OK = 'OK'
    YES = 'Yes'
    NO = 'No'

class InstrumentProperty(object):
    __gtype_name__ = 'SAXSCtrl_InstrumentProperty'
    name = None
    refreshinterval = None
    timeout = None
    type = None
    custom_is_error = None
    custom_is_warning = None
    custom_categorize = None
    def __init__(self, **kwargs):
        for name in kwargs.keys():
            self.__setattr__(name, kwargs[name])
            del kwargs[name]
    def __get__(self, obj, type=None):
        if obj is None:
            return self
        if not ((self.name in obj._instrumentproperties) and (time.time() - obj._instrumentproperties[self.name][1] <= self.timeout)):
            obj._update_instrumentproperties(self.name)
        return obj._instrumentproperties[self.name][0]
    def _update(self, obj, value, category):
        try:
            oldtuple = obj._instrumentproperties[self.name]
            if oldtuple[0] != value:
                raise KeyError
            obj._instrumentproperties[self.name] = (oldtuple[0], time.time(), oldtuple[2])
        except KeyError:
            obj._instrumentproperties[self.name] = (value, time.time(), category)
            obj._threadsafe_emit('instrumentproperty-notify', self.name)
            if self.is_error(value):
                obj._threadsafe_emit('instrumentproperty-error', self.name)
            elif self.is_warning(value):
                obj._threadsafe_emit('instrumentproperty-warning', self.name)
        return True
    def is_error(self, value):
        if callable(self.custom_is_error):
            return self.custom_is_error(value)
        else:
            return False
    def is_warning(self, value):
        if callable(self.custom_is_warning):
            return self.custom_is_warning(value)
        else:
            return False
    def categorize(self, value):
        if callable(self.custom_categorize):
            return self.custom_categorize(value)
        else:
            if self.is_error(value):
                return InstrumentPropertyCategory.ERROR
            elif self.is_warning(value):
                return InstrumentPropertyCategory.WARNING
            else:
                return InstrumentPropertyCategory.NORMAL
        

class Instrument(objwithgui.ObjWithGUI):
    __gsignals__ = {'controller-error':(GObject.SignalFlags.RUN_FIRST, None, (object,)),  # the instrument should emit this if a communication error occurs. The parameter is usually a string describing what went wrong.
                    'connect-equipment': (GObject.SignalFlags.RUN_FIRST, None, ()),  # emitted when a successful connection to the instrument is done.
                    'disconnect-equipment': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),  # emitted when the connection is broken either normally (bool argument is True) or because of an error (bool argument is false)
                    'idle': (GObject.SignalFlags.RUN_FIRST, None, ()),  # emitted whenever the instrument becomes idle, i.e. the status parameter changes to something considered as idle state (checked by the class attribute _considered_idle) 
                    'notify': 'override',
                    'instrumentproperty-error':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'instrumentproperty-warning':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'instrumentproperty-notify':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    }
    logfile = GObject.property(type=str, default='', blurb='Log file')
    logtimeout = GObject.property(type=float, default=5, minimum=1, blurb='Logging interval (sec)')
    offline = GObject.property(type=bool, default=True, blurb='Off-line mode')
    status = GObject.property(type=str, default=InstrumentStatus.Disconnected, blurb='Instrument status')
    _considered_idle = [InstrumentStatus.Idle, InstrumentStatus.Disconnected]
    timeout = GObject.property(type=float, minimum=0, default=1.0, blurb='Timeout on wait-for-reply (sec)')  # communications timeout in seconds
    configfile = GObject.property(type=str, default='', blurb='Instrument configuration file')
    _enable_instrumentproperty_signals = None
    def __init__(self, offline=True):
        self._instrumentproperties = {}
        self._OWG_init_lists()
        self._OWG_nosave_props.append('status')
        self._OWG_nogui_props.append('status')
        objwithgui.ObjWithGUI.__init__(self)
        self.offline = offline
        if not self.configfile:
            self.configfile = os.path.expanduser('~/.config/credo/' + self._get_classname() + '.conf')
        self._logthread = None
        self._logthread_stop = threading.Event()
        self._enable_instrumentproperty_signals = threading.Event()
    def do_instrumentproperty_notify(self, propertyname):
        logger.debug('InstrumentProperty %s changed to: %s' % (propertyname, str(self.get_property(propertyname))))
    def do_instrumentproperty_error(self, propertyname):
        logger.error('%s is in ERROR state (value: %s)' % (propertyname, str(self.get_property(propertyname))))
    def do_instrumentproperty_warning(self, propertyname):
        logger.warning('%s is in WARNING state (value: %s)' % (propertyname, str(self.get_property(propertyname))))
    def is_instrumentproperty(self, propertyname):
        return isinstance(getattr(type(self), propertyname), InstrumentProperty)
    def _threadsafe_emit(self, signalname, *args):
        if self._enable_instrumentproperty_signals.is_set():
            GObject.idle_add(lambda signalname, args: self.emit(signalname, *args) and False, signalname, args)
    def set_enable_instrumentproperty_signals(self, status):
        if status:
            self._enable_instrumentproperty_signals.set()
        else:
            self._enable_instrumentproperty_signals.clear()
    def get_enable_instrumentproperty_signals(self):
        return self._enable_instrumentproperty_signals.is_set()
    def get_property(self, propertyname):
        try:
            return objwithgui.ObjWithGUI.get_property(self, propertyname)
        except TypeError as te:
            return getattr(self, propertyname)
    def get_instrument_property(self, propertyname):
        return (self.get_property(propertyname), self._instrumentproperties[propertyname][1], self._instrumentproperties[propertyname][2])
    def _update_instrumentproperties(self, propertyname=None):
        raise NotImplementedError
    def _restart_logger(self):
        self._stop_logger()
        self._logthread = threading.Thread(target=self._logger_thread, args=(self._logthread_stop,))
        self._logthread.daemon = True
        self._logthread_stop.clear()
        self._logthread.start()
        logger.info('(Re)started instrument logger thread for instrument ' + self._get_classname() + '. Target: ' + self.logfile + ', timeout: %.2f sec' % self.logtimeout)
    def _stop_logger(self):
        if hasattr(self, '_logthread') and self._logthread is not None:
            self._logthread_stop.set()
            self._logthread.join()
            del self._logthread
    def _logger_thread(self, stopswitch):
        try:
            while True:
                if not self.connected():
                    break
                self._logthread_worker()
                if stopswitch.wait(self.logtimeout):
                    logger.debug('Stopping logger thread')
                    break
        except Exception as ex:
            logger.error('Breaking logger thread of instrument ' + self._get_classname() + ' because of an error: ' + str(type(ex)) + str(ex.message))
    def _logthread_worker(self):
        raise NotImplementedError
    def connect_to_controller(self):
        """Connect to the controller. The actual connection parameters (e.g. host, port etc.) 
        to be used should be implemented as GObject properties. This should work as follows:
        
        1) establish connection (open socket, serial device etc.)
        2) call self._post_connect()
        3) set status to InstrumentStatus.Idle
        4) emit signal connect-equipment
        
        If anything goes wrong during phases 1-3 of the above described procedure, the
        connection should be torn down (not by calling disconnect_from_controller and not 
        calling _pre_disconnect()), and no signal should be emitted. If the call to 
        emit('connect-equipment) raises an exception, the connection is to be considered
        valid and successful, but the exception should be propagated.
        """
        raise NotImplementedError
    def disconnect_from_controller(self, status=True):
        """Disconnect from the controller. Status signifies the cause of disconnection: True
        if this was intentional and originated from our side, False means that the disconnection
        is due to an error from either our side or the other. The procedure is as follows:
        
        1) call self._pre_disconnect() the bool status as the argument. Exceptions raised should be
        ignored.
        2) break down the connection (close socket, free the serial device etc.)
        3) emit disconnect-equipment with the bool status.
        
        Exceptions during all phases should be re-raised at the end (or at least logged), but the
        disconnection should be carried out in every case.
        
        """
        raise NotImplementedError
    def connected(self):
        """Check if we have an open connection to the instrument. It is enough to check if the
        connection is open, we do not have to check if we can contact the instrument through it.
        However, if a subsequent communication request to the instrument fails, the connection
        should be closed down by calling disconnect_from_controller(False).
        """
        raise NotImplementedError
    def _post_connect(self):
        """Do initialization tasks after a connection has been established. This is called from
        connect_to_controller() after the connection is established (e.g. socket opened). If an
        exception is raised, connect_controller() will catch it and close down the connection.
        
        If you install timeout or idle handlers (a la GObject), you should not close them in the
        _pre_disconnect() method. Instead, put a check to self.connected() at the beginning of the
        handler, and return False if no connection exists. In other words, if you raise an
        exception, you should rely on _pre_disconnect() to be called at all.
        
        If the communications involves a lock, this method is called with the lock already acquired.
        """
        pass
    def _pre_disconnect(self, should_do_communication):
        """Do finalization tasks before the actual connection is closed. The argument is a bool,
        which signifies if the connection is alive, or we are getting called because an abnormal
        connection break happened. The communications lock is not acquired when this function is called.
        """
        pass
    def send_and_receive(self, command, blocking=True):
        """Do whatever it takes to send "command" (usually a string) to the controller. If "blocking"
        is True, you should wait for the reply (timeout is defined in the "timeout" property) and
        return it after calling interpret_message(replymessage, command). If "blocking" is False,
        you should return None. 
        """
        raise NotImplementedError
    def interpret_message(self, message, command=None):
        """Interpret incoming message (e.g. validate checksum or do some processing). The argument
        "command" can be a hint: it can (should) be the command to which "message" is a reply. 
        In case of an asynchronous message, "command" should be None. This is usually called
        by send_and_receive(), or by a collector thread collecting asynchronous messages."""
        raise NotImplementedError
    def is_idle(self):
        return self.status in self._considered_idle
    def do_notify(self, prop):
        logger.debug('Instrument:notify: ' + prop.name + ' (class: ' + self._get_classname() + ') set to: ' + str(self.get_property(prop.name)))
        if prop.name == 'status' and self.is_idle():
            self.emit('idle')
        elif prop.name == 'logfile':
            if not os.path.isabs(self.logfile):
                self.logfile = os.path.abspath(self.logfile)
            else:
                if self.connected():
                    self._restart_logger()
            
    def get_current_parameters(self):
        """Return a dictionary of the current status (characteristics) of the instrument. E.g. in
        case of an X-ray source, these can be the current high tension, current, shutter state etc.
        
        The main intention to this is to be able to collect the status information of all instruments
        in order to save them (e.g. in the header file of a SAXS exposure).
        """
        return {}
    def wait_for_idle(self, alternative_breakfunc=lambda :False):
        """Wait until the instrument becomes idle or alternative_breakfunc() returns True. 
        During the wait, this calls the default GObject main loop.
        """
        while not (self.is_idle() or alternative_breakfunc()):
            for i in range(100):
                GObject.main_context_default().iteration(False)
                if not GObject.main_context_default().pending():
                    break
        return (not alternative_breakfunc())
    def wait_for_status(self, desiredstatus, alternative_breakfunc=lambda :False):
        """Wait until the instrument comes into the desired state or alternative_breakfunc() returns True. 
        During the wait, this calls the default GObject main loop.
        """
        while not (self.status == desiredstatus or alternative_breakfunc()):
            for i in range(100):
                GObject.main_context_default().iteration(False)
                if not GObject.main_context_default().pending():
                    break
        return (not alternative_breakfunc())
    def _get_address(self):
        raise NotImplementedError
    def _set_address(self, address):
        raise NotImplementedError
    def __ga(self):
        return self._get_address()
    def __sa(self, address):
        return self._set_address(address)
    address = property(__ga, __sa, None, 'Address of the instrument')
        
class CommunicationCollector(threading.Thread):
    def __init__(self, parent, queue, lock, sleep=0.1, mesgseparator=None):
        threading.Thread.__init__(self, name=self.__class__.__name__)
        self.parent = weakref.ref(parent)
        self.queue = queue
        self.lock = lock
        self.kill = threading.Event()
        self.sleeptime = sleep
        self.mesgseparator = mesgseparator
        logger.debug('Initialized CommunicationCollector thread with sleep time %f' % self.sleeptime)
    def do_read(self):
        raise NotImplementedError
    def run(self):
        while not self.kill.wait(self.sleeptime):
            if not self.lock.acquire(False):
                continue
            try:
                mesg = self.do_read()
            except ConnectionBrokenError:
                logger.warning('Communication error in communicationcollector thread: shutting down socket.')
                self.lock.release()
                self.parent().disconnect_from_controller(False)
                break
            else:
                self.lock.release()
            if mesg is not None:
                if self.mesgseparator is not None:
                    for m in [m for m in mesg.split(self.mesgseparator) if m]:  # skip empty parts, e.g. when the message ends in a separator.
                        self.queue.put(m)
                else:
                    self.queue.put(mesg)
        logger.debug('Communication collector thread ending.')
        
        
class Instrument_ModbusTCP(Instrument):
    host = GObject.property(type=str, default='', blurb='Host name')
    port = GObject.property(type=int, minimum=0, default=502, blurb='Port number')
    def __init__(self, offline=True):
        self._communications_lock = multiprocessing.Lock()
        self._modbus = None
        Instrument.__init__(self, offline)
    def connected(self):
        return self._modbus is not None
    def connect_to_controller(self):
        if self.offline:
            raise InstrumentError('Cannot connect to controller: we are off-line')
        with self._communications_lock:
            if self.connected():
                raise InstrumentError('Already connected')
            self._modbus = modbus_tk.modbus_tcp.TcpMaster(self.host, self.port)
            self._modbus.set_timeout(self.timeout)
            try:
                self._modbus.open()
                self._post_connect()
                self.status = InstrumentStatus.Idle
                self._restart_logger()
            except (socket.timeout, InstrumentError) as ex:
                self._modbus = None
                logger.error('Cannot connect to instrument at %s:%d' % (self.host, self.port))
                raise InstrumentError('Cannot connect to instrument at %s:%d. Reason: %s' % (self.host, self.port, ex.message))
        logger.info('Connected to instrument at %s:%d' % (self.host, self.port))
        self.emit('connect-equipment')
            
    def disconnect_from_controller(self, status):
        if not self.connected():
            raise InstrumentError('Not connected')
        self._pre_disconnect(status)
        with self._communications_lock:
            self._stop_logger()
            self._modbus.close()
            self._modbus = None
            self.status = InstrumentStatus.Disconnected
            self.emit('disconnect-equipment', status)
            
    def do_controller_error(self, arg):
        if self.connected():
            self.disconnect_from_controller(False)
    def _read_integer(self, regno):
        with self._communications_lock:
            try:
                return self._modbus.execute(1, modbus_tk.defines.READ_INPUT_REGISTERS, regno, 1)[0]
            except Exception as exc:
                GObject.idle_add(lambda :(self.emit('controller-error', None) and False))
                raise InstrumentError('Communication error on reading integer value: ' + exc.message)
    def _write_coil(self, coilno, val):
        with self._communications_lock:
            try:
                self._modbus.execute(1, modbus_tk.defines.WRITE_SINGLE_COIL, coilno, 1, val)
            except Exception as exc:
                GObject.idle_add(lambda :(self.emit('controller-error', None) and False))
                raise InstrumentError('Communication error on writing coil: ' + exc.message)
    def _read_coils(self, coilstart, coilnum):
        with self._communications_lock:
            try:
                coils = self._modbus.execute(1, modbus_tk.defines.READ_COILS, coilstart, coilnum)
            except Exception as exc:
                GObject.idle_add(lambda :(self.emit('controller-error', None) and False))
                raise InstrumentError('Communication error on reading coils: ' + exc.message)
            return coils
    def _get_address(self):
        return self.host + ':' + str(self.port)
    def _set_address(self, address):
        if ':' in address:
            host, port = address.split(':', 1)
            port = int(port)
            self.host = host
            self.port = port
        else:
            self.host = address
            
class Instrument_TCP(Instrument):
    host = GObject.property(type=str, default='', blurb='Host name')
    port = GObject.property(type=int, minimum=0, default=41234, blurb='Port number')
    timeout2 = GObject.property(type=float, minimum=0, default=0.01, blurb='Timeout on read-reply')
    recvbufsize = GObject.property(type=int, minimum=0, default=100, blurb='Size of receiving buffer minus one')
    _mesgseparator = None
    collector_sleep = GObject.property(type=float, minimum=0, default=0.1, blurb='Sleeping time for collector thread.')
    _commands = None
    def __init__(self, offline=True):
        self._socket = None
        self._socketlock = multiprocessing.Lock()
        self._inqueue = multiprocessing.queues.Queue()
        Instrument.__init__(self, offline)

    def connect_to_controller(self):
        if self.offline:
            raise InstrumentError('Cannot connect to controller: we are off-line')
        with self._socketlock:
            if self.connected():
                raise InstrumentError('Cannot connect: already connected.')
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                ip = socket.gethostbyname(self.host)
                self._socket.connect((ip, self.port))
                logger.debug('Connected to TCP socket at %s:%d' % (self.host, self.port))
            except socket.gaierror:
                self._socket = None
                raise InstrumentError('Cannot resolve host name.')
            except socket.error:
                self._socket = None
                raise InstrumentError('Cannot establish TCP connection to instrument.')
            self._socket.settimeout(self.timeout)
            self._socket.setblocking(False)
        try:
            logger.debug('Starting up reply collector thread for socket %s:%d' % (self.host, self.port))
            GObject.idle_add(self._check_inqueue)
            self._collector = CommunicationCollector_TCP(self._socket, self, self._inqueue, self._socketlock, self.collector_sleep, mesgseparator=self._mesgseparator)
            self._collector.daemon = True
            self._collector.start()
            logger.debug('Running post-connect.')
            self._post_connect()
            logger.debug('Post-connect finished successfully.')
            self.status = InstrumentStatus.Idle
            self._restart_logger()
        except InstrumentError as ex:
            logger.debug('InstrumentError exception during post-socket-setup initialization.')
            if hasattr(self, '_collector'):
                logger.debug('Stopping collector thread')
                self._collector.kill.set()
                try:
                    self._collector.join()
                except RuntimeError:
                    pass
                logger.debug('Collector thread stopped.')
            with self._socketlock:
                if self._socket is not None:
                    self._socket.close()
                    self._socket = None
            raise InstrumentError('Error while connecting to instrument at %s:%d: %s' % (self.host, self.port, ex.message))
        logger.info('Connected to instrument at %s:%d' % (self.host, self.port))
        self.emit('connect-equipment')
    def connected(self):
        return self._socket is not None
    def disconnect_from_controller(self, status=True):
        try:
            self._pre_disconnect(status)
        except:
            pass
        with self._socketlock:
            logger.debug('Disconnecting.')
            self._stop_logger()
            self._collector.kill.set()
            try:
                self._collector.join()
            except RuntimeError:
                pass
            if not self.connected(): return
            try:
                self._socket.close()
            except socket.error:
                pass
            finally:
                self._socket = None
        self.status = InstrumentStatus.Disconnected
        self.emit('disconnect-equipment', status)
    def _read_from_socket(self, timeout=None):
        message = None
        try:
            if timeout is None:
                timeout = self.timeout
            # read the first character of the reply with the given timeout value.
            # if no message is waiting, this will raise an exception, which we will
            # catch. Otherwise we try to continue with the other characters. 
            rlist, wlist, xlist = select.select([self._socket], [], [self._socket], timeout)
            if xlist:
                raise ConnectionBrokenError('socket is exceptional on starting phase of read')
            if not rlist:
                raise InstrumentTimeoutError('socket is not readable on starting phase of read')
            message = self._socket.recv(1)
            # read subsequent characters with zero timeout. We do this in order to
            # avoid waiting too long after the end of each message, and to use 
            # the one-recv-per-char technique, which can be dead slow. This way we
            # can use a larger buffer size in recv(), and if fewer characters are
            # waiting in the input buffer, the zero timeout will ensure that we are
            # not waiting in vain.
            while True:
                rlist, wlist, xlist = select.select([self._socket], [], [self._socket], self.timeout2)
                if xlist:
                    raise ConnectionBrokenError('socket is exceptional on second phase of read')
                if not rlist:
                    raise InstrumentTimeoutError('socket is not readable on second phase of read')
                # if the input message ended, and nothing is to be read, an exception
                # will be raised, which we will catch.
                mesg = self._socket.recv(self.recvbufsize)
                if mesg == '': 
                    # if no exception is raised and an empty string has been read, it
                    # signifies that the connection has been broken.
                    raise ConnectionBrokenError('empty string read from socket: other end hung up.')
                message = message + mesg
        except InstrumentTimeoutError as ite:
            # this signifies the end of message, or a timeout when reading the first char.
            # In the former case, we simply ignore this condition. In the latter, we raise
            # an exception.
            if message is None:
                raise InstrumentError('Timeout while reading reply: ' + ite.message)
        except ConnectionBrokenError as cbe:
            # this is a serious error, we tear down the connection on our side.
            # We call the disconnecting method in this funny way, since it needs locking
            # self._socket_lock, which is now locked.
            GObject.idle_add(lambda :(self.disconnect_from_controller(False) and False))
            raise cbe
        except socket.error as se:
            raise InstrumentError('Communication Error: ' + se.message) 
        finally:
            self._socket.settimeout(self.timeout)
        return message
    
    def send_and_receive(self, command, blocking=True):
        with self._socketlock:
            self._socket.sendall(command)
            if not blocking: return None
            if isinstance(blocking, float):
                message = self._read_from_socket(blocking)
            else:
                message = self._read_from_socket(None)
            if (self._mesgseparator is not None) and message.endswith(self._mesgseparator):
                message = message[:-len(self._mesgseparator)]
            if (self._mesgseparator is not None) and self._mesgseparator in message:
                # if multiple messages received, only keep the first one which matches the current command,
                # if the list of the available commands (self._commands) is defined (is not None)
                try:
                    cmd = self._get_command(command)
                    mymessage = [m for m in message.split(self._mesgseparator) if cmd.match(m) is not None][0]
                    othermessages = [m for m in message.split(self._mesgseparator) if m != mymessage]
                except (TypeError, IndexError, AttributeError) as excep:
                    mymessage = message.split(self._mesgseparator)[0]
                    othermessages = message.split(self._mesgseparator)[1:]
                for m in othermessages:
                    self._inqueue.put(m)
                return mymessage
            else:
                return message
    def _get_command(self, command):
        try:
            return [c for c in self._commands if c.command.lower() == command.lower()][0]
        except (AttributeError, IndexError):
            return None
    def _check_inqueue(self):
        try:
            mesg = self._inqueue.get_nowait()
        except multiprocessing.queues.Empty:
            # this ensures that whenever the equipment gets disconnected, all the pending messages are processed before this
            # idle function is removed.
            return self.connected()
        self.interpret_message(mesg, None)
        return True
    def _get_address(self):
        return self.host + ':' + str(self.port)
    def _set_address(self, address):
        if ':' in address:
            host, port = address.split(':', 1)
            port = int(port)
            self.host = host
            self.port = port
        else:
            self.host = address


            
class CommunicationCollector_TCP(CommunicationCollector):
    # ## socket should have a reasonable timeout (e.g. 0.001, but not zero).
    def __init__(self, sock, parent, queue, lock, sleep=0.1, mesgseparator=None):
        self.socket = sock
        CommunicationCollector.__init__(self, parent, queue, lock, sleep, mesgseparator)
    def do_read(self):
        message = ''
        while True:
            rlist, wlist, xlist = select.select([self.socket], [], [self.socket], 0.001)
            if xlist:
                raise ConnectionBrokenError()
            if not rlist:
                break
            try:
                mesg = self.socket.recv(1024)
            except (socket.timeout, socket.error):
                logger.warning('Socket error in CommunicationCollector')
                return message
            message = message + mesg
            if mesg == '':
                # this signifies that the other end of the connection broke.
                raise ConnectionBrokenError
        if message == '':
            # nothing has been read
            return None
        return message
        

class CommandReply(object):
    """This class implements a reply to a command. Each command can have multiple replies.
    Replies are parsed by default by regular expression matching, but this behaviour can
    be overridden by subclassing and modifying the match() method."""
    def __init__(self, regex, findall_regex=None, defaults=None):
        self.regex = re.compile(r'^' + regex + '$', re.MULTILINE)
        self.findall_regex = findall_regex
        if defaults is None:
            self.defaults = {}
        else:
            self.defaults = defaults
            
    def match(self, message):
        m = self.regex.match(message)
        if m is None:
            return None
        else:
            gd = m.groupdict()
            # try to apply findall_regex: usefuly e.g. in the THread camserver
            # command, where multiple phrases of the same format are present.
            if self.findall_regex is not None:
                for submatch in re.finditer(self.findall_regex, message):
                    # for each repetition of the phrase, collect the values
                    # in a list.
                    for g in submatch.groupdict():
                        if (g not in gd) or (not isinstance(gd[g], list)):
                            gd[g] = []
                        gd[g].append(submatch.groupdict()[g])
            ret = self.defaults.copy()
            ret.update(gd)
            return ret

        
class Command(object):
    """This class represents a command to the Pilatus Camserver.
    
    Attributes are:
        command: the command as a string.
        replies: a list of CommandReply objects matching the possible outcomes
            of the command.
        argconverters: a dictionary mapping the argument name to a type, e.g.
            {'tau':float, 'cutoff':int}
    """
    def __init__(self, command, replies, argconverters={}):
        self.command = command
        self.replies = replies
        self.conv = argconverters
        pass
    def match(self, message):
        # find a matching reply
        for r in self.replies:
            if r is None:
                continue
            m = r.match(message)
            if m is None:
                # if this regex does not match, continue with the next.
                continue
            # convert the values to the given type.
            for k in self.conv:
                if k in m and m[k] is not None:
                    m[k] = self.conv[k](m[k])
            return m
        # if no reply matched, return.
        return None
