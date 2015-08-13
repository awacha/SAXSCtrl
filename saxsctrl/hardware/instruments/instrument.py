from gi.repository import GObject
from gi.repository import GLib
import logging
import socket
import queue
import threading
import weakref
import re
import multiprocessing
import select
from pyModbusTCP.client import ModbusClient
import os
import time
import numpy as np
from ...utils import objwithgui
import traceback
import collections
import binascii

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class InstrumentError(Exception):
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


class InstrumentPropertyUnknown(Exception):
    pass


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
        for name in list(kwargs.keys()):
            self.__setattr__(name, kwargs[name])
            del kwargs[name]

    def __get__(self, obj, type_=None):
        if obj is None:
            return self
        if not ((self.name in obj._instrumentproperties) and (time.time() - obj._instrumentproperties[self.name][1] <= self.timeout)):
            obj._update_instrumentproperties(self.name)
        if obj._instrumentproperties[self.name][2] == InstrumentPropertyCategory.UNKNOWN:
            raise InstrumentPropertyUnknown(self.name)
        return obj._instrumentproperties[self.name][0]

    def _update(self, obj, value, category):
        try:
            oldtuple = obj._instrumentproperties[self.name]
            if oldtuple[0] != value:
                raise KeyError
            obj._instrumentproperties[self.name] = (
                oldtuple[0], time.time(), oldtuple[2])
        except KeyError:
            obj._instrumentproperties[self.name] = (
                value, time.time(), category)
            obj._threadsafe_emit('instrumentproperty-notify', self.name)
            if self.is_error(value) or (category == InstrumentPropertyCategory.ERROR):
                obj._threadsafe_emit('instrumentproperty-error', self.name)
            elif self.is_warning(value) or (category == InstrumentPropertyCategory.WARNING):
                obj._threadsafe_emit('instrumentproperty-warning', self.name)
        return True

    def is_error(self, value):
        if isinstance(self.custom_is_error, collections.Callable):
            return self.custom_is_error(value)
        else:
            return False

    def is_warning(self, value):
        if isinstance(self.custom_is_warning, collections.Callable):
            return self.custom_is_warning(value)
        else:
            return False

    def categorize(self, value):
        if isinstance(self.custom_categorize, collections.Callable):
            return self.custom_categorize(value)
        else:
            if self.is_error(value):
                return InstrumentPropertyCategory.ERROR
            elif self.is_warning(value):
                return InstrumentPropertyCategory.WARNING
            else:
                return InstrumentPropertyCategory.NORMAL


class Instrument(objwithgui.ObjWithGUI):
    __gsignals__ = {'controller-error': (GObject.SignalFlags.RUN_FIRST, None, (object,)),  # the instrument should emit this if a communication error occurs. The parameter is usually a string describing what went wrong.
                    # emitted when a successful connection to the instrument is
                    # done.
                    'connect-equipment': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    # emitted when the connection is broken either normally
                    # (bool argument is True) or because of an error (bool
                    # argument is false)
                    'disconnect-equipment': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    # emitted whenever the instrument becomes idle, i.e. the
                    # status parameter changes to something considered as idle
                    # state (checked by the class attribute _considered_idle)
                    'idle': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    'notify': 'override',
                    'instrumentproperty-error': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'instrumentproperty-warning': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'instrumentproperty-notify': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    }
    logfile = GObject.property(type=str, default='', blurb='Log file')
    logtimeout = GObject.property(
        type=float, default=5, minimum=1, blurb='Logging interval (sec)')
    offline = GObject.property(type=bool, default=True, blurb='Off-line mode')
    status = GObject.property(
        type=str, default=InstrumentStatus.Disconnected, blurb='Instrument status')
    _considered_idle = [InstrumentStatus.Idle, InstrumentStatus.Disconnected]
    # communications timeout in seconds
    timeout = GObject.property(
        type=float, minimum=0, default=1.0, blurb='Timeout on wait-for-reply (sec)')
    configfile = GObject.property(
        type=str, default='', blurb='Instrument configuration file')
    reconnect_interval = GObject.property(
        type=float, minimum=0, default=1, blurb='Interval for reconnect attempts after a sudden connection breakage')
    reconnect_attempts_number = GObject.property(
        type=int, minimum=0, default=3, blurb='Number of times reconnection is attempted after a sudden connection breakage')
    _enable_instrumentproperty_signals = None
    _logging_parameters = []

    def __init__(self, name=None, offline=True):
        self._instrumentproperties = {}
        if name is None:
            name = 'Unnamed instrument'
        self._name = name
        self._OWG_init_lists()
        self._OWG_nosave_props.append('status')
        self._OWG_nogui_props.append('status')
        objwithgui.ObjWithGUI.__init__(self)
        self.offline = offline
        if not self.configfile:
            self.configfile = os.path.expanduser(
                os.path.join('config', self._get_classname() + '.conf'))
        self._logthread = None
        self._logthread_stop = threading.Event()
        self._enable_instrumentproperty_signals = threading.Event()

    def _get_classname(self):
        return objwithgui.ObjWithGUI._get_classname(self) + '__' + self._name

    def do_instrumentproperty_notify(self, propertyname):
        try:
            logger.debug('InstrumentProperty %s changed to: %s' %
                         (propertyname, str(self.get_property(propertyname))))
        except InstrumentPropertyUnknown:
            logger.debug('InstrumentProperty %s is now unknown.' %
                         propertyname)

    def do_instrumentproperty_error(self, propertyname):
        logger.error('%s is in ERROR state (value: %s)' %
                     (propertyname, str(self.get_property(propertyname))))

    def do_instrumentproperty_warning(self, propertyname):
        logger.warning('%s is in WARNING state (value: %s)' %
                       (propertyname, str(self.get_property(propertyname))))

    def is_instrumentproperty(self, propertyname):
        return isinstance(getattr(type(self), propertyname), InstrumentProperty)

    def is_instrumentproperty_expired(self, propertyname):
        return ((propertyname not in self._instrumentproperties) or
                (time.time() - self._instrumentproperties[propertyname][1]) > getattr(type(self), propertyname).timeout or
                self._instrumentproperties[propertyname][2] == InstrumentPropertyCategory.UNKNOWN)

    def _threadsafe_emit(self, signalname, *args):
        if self._enable_instrumentproperty_signals.is_set():
            GLib.idle_add(lambda signalname, args: self.emit(
                signalname, *args) and False, signalname, args)

    def _threadsafe_set_property(self, propname, value):
        def _handler(sel, pn, v):
            if sel.get_property(pn) != v:
                sel.set_property(pn, v)
            # because we are called as an idle function and don't want to be
            # called again
            return False
        GLib.idle_add(_handler, self, propname, value)

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
        except TypeError:
            return getattr(self, propertyname)

    def get_instrument_property(self, propertyname):
        try:
            value = self.get_property(propertyname)
        except InstrumentPropertyUnknown:
            value = None
        return (value, self._instrumentproperties[propertyname][1], self._instrumentproperties[propertyname][2])

    def _update_instrumentproperties(self, propertyname=None):
        raise NotImplementedError

    def _get_instrumentproperties(self):
        return [x for x in dir(type(self)) if isinstance(getattr(type(self), x), InstrumentProperty)]

    def _invalidate_instrumentproperties(self):
        for ip in self._get_instrumentproperties():
            self._instrumentproperties[ip] = (
                None, 0, InstrumentPropertyCategory.UNKNOWN)

    def _restart_logger(self):
        self._stop_logger()
        self._logthread = threading.Thread(
            target=self._logger_thread, args=(self._logthread_stop,))
        self._logthread.daemon = True
        self._logthread_stop.clear()
        self._logthread.start()
        logger.info('(Re)started instrument logger thread for instrument ' + self._get_classname() +
                    '. Target: ' + self.logfile + ', timeout: %.2f sec' % self.logtimeout)

    def _stop_logger(self):
        if hasattr(self, '_logthread') and self._logthread is not None:
            self._logthread_stop.set()
            self._logthread.join()
            del self._logthread

    def _logger_thread(self, stopswitch):
        if not self._logging_parameters:
            return
        with open(self.logfile, 'at') as f:
            f.write('#Time\t' + '\t'.join(x[0]
                                          for x in self._logging_parameters) + '\n')
        try:
            self._update_instrumentproperties(None)
            while True:
                if not self.connected():
                    break
                try:
                    self._logthread_worker()
                except ConnectionBrokenError as ex:
                    raise ex
                except InstrumentError as ex:
                    logger.warn('Non-fatal exception in logger thread of instrument ' +
                                self._get_classname() + ': ' + traceback.format_exc())
                except Exception as ex:
                    logger.critical('Unhandleable exception in logger thread of instrument ' +
                                    self._get_classname() + ': ' + traceback.format_exc())
                    raise ex
                if stopswitch.wait(self.logtimeout):
                    logger.debug('Stopping logger thread')
                    break
        except Exception as ex:
            logger.error('Breaking logger thread of instrument ' + self._get_classname() +
                         ' because of an error: ' + traceback.format_exc())

    def _logformatstring(self):
        return '%.1f\t' + ('\t'.join([x[2] for x in self._logging_parameters])) + '\n'

    def _logdtype(self):
        return np.dtype([('time', 'f4')] + [x[:2] for x in self._logging_parameters])

    def _get_logline(self):
        return self._logformatstring() % ((time.time(),) + tuple(getattr(self, x[0]) for x in self._logging_parameters))

    def _logthread_worker(self):
        with open(self.logfile, 'at') as f:
            f.write(self._get_logline())

    def load_log(self):
        return np.loadtxt(self.logfile, dtype=self._logdtype(), delimiter='\t')

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

    def disconnect_from_controller(self, status=True, reconnect=False):
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

    def __idle__(self, status):
        raise NotImplementedError

    def is_idle(self):
        try:
            return self.__idle__(self.status)
        except:
            return self.status in self._considered_idle

    def do_notify(self, prop):
        logger.debug('Instrument:notify: ' + prop.name + ' (class: ' + self._get_classname() + ') set to: ' +
                     str(self.get_property(prop.name)) + '. (Thread: ' + threading.current_thread().name + ')')
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

    def wait_for_idle(self, alternative_breakfunc=lambda: False):
        """Wait until the instrument becomes idle or alternative_breakfunc() returns True.
        During the wait, this calls the default GObject main loop.
        """
        while not (self.is_idle() or alternative_breakfunc()):
            for i in range(100):
                GLib.main_context_default().iteration(False)
                if not GLib.main_context_default().pending():
                    break
        return (not alternative_breakfunc())

    def wait_for_status(self, desiredstatus, alternative_breakfunc=lambda: False):
        """Wait until the instrument comes into the desired state or alternative_breakfunc() returns True.
        During the wait, this calls the default GObject main loop.
        """
        while not (self.status == desiredstatus or alternative_breakfunc()):
            for i in range(100):
                GLib.main_context_default().iteration(False)
                if not GLib.main_context_default().pending():
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

    def reconnect_to_controller_after_error(self, remaining=0):
        try:
            self.connect_to_controller()
        except InstrumentError:
            logger.warning('Reconnect attempt %d/%d failed.' % (
                self.reconnect_attempts_number - remaining + 1, self.reconnect_attempts_number))
            if remaining > 1:
                GLib.timeout_add_seconds(
                    self.reconnect_interval, self.reconnect_to_controller_after_error, remaining - 1)
            else:
                logger.error('Could not reconnect to controller.')
        except:
            logger.error(
                'Could not reconnect to controller: other error. Expect an upcoming critical error message with the details.')
            raise
        else:
            logger.info('Successful reconnection to controller.')
        return False  # deregister GLib timeout handler


class CommunicationCollector(threading.Thread):

    def __init__(self, parent, queue, lock, sleep=0.1, mesgseparator=None):
        threading.Thread.__init__(self, name=self.__class__.__name__)
        self.parent = weakref.ref(parent)
        self.queue = queue
        self.lock = lock
        self.kill = threading.Event()
        self.sleeptime = sleep
        self.mesgseparator = mesgseparator
        logger.debug(
            'Initialized CommunicationCollector thread with sleep time %f' % self.sleeptime)

    def do_read(self):
        raise NotImplementedError

    def run(self):
        while not self.kill.wait(self.sleeptime):
            if not self.lock.acquire(False):
                continue
            try:
                mesg = self.do_read()
            except ConnectionBrokenError as cbe:
                logger.warning(
                    'Communication error in communicationcollector thread: shutting down socket. Error: %s' % traceback.format_exc())
                self.lock.release()
                self.parent().disconnect_from_controller(False, reconnect=True)
                break
            else:
                self.lock.release()
            if mesg is not None:
                if self.mesgseparator is not None:
                    # skip empty parts, e.g. when the message ends in a
                    # separator.
                    for m in [m for m in mesg.split(self.mesgseparator) if m]:
                        self.queue.put(m)
                else:
                    self.queue.put(mesg)
        logger.debug('Communication collector thread ending.')


class Instrument_ModbusTCP(Instrument):
    host = GObject.property(type=str, default='', blurb='Host name')
    port = GObject.property(
        type=int, minimum=0, default=502, blurb='Port number')

    def __init__(self, name=None, offline=True):
        self._communications_lock = multiprocessing.RLock()
        self._modbus = None
        Instrument.__init__(self, name, offline)

    def connected(self):
        return self._modbus is not None

    def connect_to_controller(self):
        if self.offline:
            raise InstrumentError(
                'Cannot connect to controller: we are off-line')
        with self._communications_lock:
            if self.connected():
                raise InstrumentError('Already connected')
            self._modbus = ModbusClient(
                self.host, self.port, timeout=self.timeout)
            try:
                if not self._modbus.open():
                    raise InstrumentError(
                        'Cannot contact to Modbus instrument.')
                self._post_connect()
                self.status = InstrumentStatus.Idle
                self._restart_logger()
            except (socket.timeout, InstrumentError, socket.error) as ex:
                self._modbus = None
                if logger.level == logging.DEBUG:
                    logger.error(
                        'Cannot connect to instrument at %s:%d' % (self.host, self.port))
                raise InstrumentError('Cannot connect to instrument at %s:%d. Reason: %s' % (
                    self.host, self.port, traceback.format_exc()))
        logger.info('Connected to instrument at %s:%d' %
                    (self.host, self.port))
        self.emit('connect-equipment')

    def disconnect_from_controller(self, status=True, reconnect=False):
        if not self.connected():
            raise InstrumentError('Not connected')
        self._stop_logger()
        self._pre_disconnect(status)
        with self._communications_lock:
            self._modbus.close()
            self._modbus = None
            self.status = InstrumentStatus.Disconnected
            self._invalidate_instrumentproperties()
            self.emit('disconnect-equipment', status)
        if reconnect:
            GLib.timeout_add_seconds(self.reconnect_interval,
                                     self.reconnect_to_controller_after_error, self.reconnect_attempts_number)

    def do_controller_error(self, arg):
        if self.connected():
            self.disconnect_from_controller(False, reconnect=True)

    def _read_integer(self, regno):
        with self._communications_lock:
            try:
                return self._modbus.read_holding_registers(regno, 1)[0]
            except Exception as exc:
                GLib.idle_add(
                    lambda: (self.emit('controller-error', None) and False))
                raise InstrumentError(
                    'Communication error on reading integer value: ' + traceback.format_exc())

    def _write_coil(self, coilno, val):
        with self._communications_lock:
            try:
                self._modbus.write_single_coil(coilno, val)
            except Exception as exc:
                GLib.idle_add(
                    lambda: (self.emit('controller-error', None) and False))
                raise InstrumentError(
                    'Communication error on writing coil: ' + traceback.format_exc())

    def _read_coils(self, coilstart, coilnum):
        with self._communications_lock:
            try:
                coils = self._modbus.read_coils(coilstart, coilnum)
            except Exception as exc:
                GLib.idle_add(
                    lambda: (self.emit('controller-error', None) and False))
                raise InstrumentError(
                    'Communication error on reading coils: ' + traceback.format_exc())
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
    port = GObject.property(
        type=int, minimum=0, default=41234, blurb='Port number')
    timeout2 = GObject.property(
        type=float, minimum=0, default=0.01, blurb='Timeout on read-reply')
    recvbufsize = GObject.property(
        type=int, minimum=0, default=100, blurb='Size of receiving buffer minus one')
    _mesgseparator = None
    collector_sleep = GObject.property(
        type=float, minimum=0, default=0.1, blurb='Sleeping time for collector thread.')
    _commands = None

    def __init__(self, name=None, offline=True):
        self._socket = None
        self._socketlock = multiprocessing.Lock()
        self._inqueue = multiprocessing.Queue()
        Instrument.__init__(self, name, offline)

    def connect_to_controller(self):
        if self.offline:
            raise InstrumentError(
                'Cannot connect to controller: we are off-line')
        with self._socketlock:
            if self.connected():
                raise InstrumentError('Cannot connect: already connected.')
            try:
                self._socket = socket.socket(
                    socket.AF_INET, socket.SOCK_STREAM)
                ip = socket.gethostbyname(self.host)
                self._socket.connect((ip, self.port))
                logger.debug('Connected to TCP socket at %s:%d' %
                             (self.host, self.port))
            except socket.gaierror:
                self._socket = None
                raise InstrumentError('Cannot resolve host name.')
            except socket.error:
                self._socket = None
                raise InstrumentError(
                    'Cannot establish TCP connection to instrument.')
            self._socket.settimeout(self.timeout2)
            self._socket.setblocking(False)
        try:
            logger.debug(
                'Starting up reply collector thread for socket %s:%d' % (self.host, self.port))
            GLib.idle_add(self._check_inqueue)
            self._collector = CommunicationCollector_TCP(
                self._socket, self, self._inqueue, self._socketlock, self.collector_sleep, mesgseparator=self._mesgseparator)
            self._collector.daemon = True
            self._collector.start()
            logger.debug('Running post-connect.')
            self._post_connect()
            logger.debug('Post-connect finished successfully.')
            self.status = InstrumentStatus.Idle
            self._restart_logger()
        except InstrumentError as ex:
            logger.debug(
                'InstrumentError exception during post-socket-setup initialization: ' + traceback.format_exc())
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
            raise InstrumentError('Error while connecting to instrument at %s:%d: %s' % (
                self.host, self.port, traceback.format_exc()))
        logger.info('Connected to instrument at %s:%d' %
                    (self.host, self.port))
        self.emit('connect-equipment')

    def connected(self):
        return self._socket is not None

    def disconnect_from_controller(self, status=True, reconnect=False):
        try:
            self._pre_disconnect(status)
        except:
            pass
        logger.debug('Disconnecting.')
        self._stop_logger()
        with self._socketlock:
            self._collector.kill.set()
            try:
                self._collector.join()
            except RuntimeError:
                pass
            if not self.connected():
                return
            try:
                self._socket.close()
            except socket.error:
                pass
            finally:
                self._socket = None
        self._invalidate_instrumentproperties()
        self.status = InstrumentStatus.Disconnected
        self.emit('disconnect-equipment', status)
        if reconnect:
            GLib.timeout_add_seconds(self.reconnect_interval,
                                     self.reconnect_to_controller_after_error, self.reconnect_attempts_number)

    def _read_from_socket(self, timeout=None):
        message = None
        try:
            if timeout is None:
                timeout = self.timeout
            # read the first character of the reply with the given timeout value.
            # if no message is waiting, this will raise an exception, which we will
            # catch. Otherwise we try to continue with the other characters.
            logger.debug('_read_from_socket: select.select()')
            rlist, wlist, xlist = select.select(
                [self._socket], [], [self._socket], timeout)
            logger.debug('_read_from_socket: select.select() ended.')
            if xlist:
                raise ConnectionBrokenError(
                    'socket is exceptional on starting phase of read')
            if not rlist:
                raise InstrumentTimeoutError(
                    'socket is not readable on starting phase of read')
            logger.debug('Receiving the first character of the message.')
            message = self._socket.recv(1)
            logger.debug('Message: ' + str(message) + '; length: %d' %
                         len(message) + ' hex: ' + str(binascii.hexlify(message)))
            if not message:
                # socket closed.
                raise ConnectionBrokenError(
                    'socket received empty message on reading first character => closed.')
            # read subsequent characters with zero timeout. We do this in order to
            # avoid waiting too long after the end of each message, and to use
            # the one-recv-per-char technique, which can be dead slow. This way we
            # can use a larger buffer size in recv(), and if fewer characters are
            # waiting in the input buffer, the zero timeout will ensure that we are
            # not waiting in vain.
            while True:
                rlist, wlist, xlist = select.select(
                    [self._socket], [], [self._socket], self.timeout2)
                if xlist:
                    raise ConnectionBrokenError(
                        'socket is exceptional on second phase of read')
                if not rlist:
                    raise InstrumentTimeoutError(
                        'socket is not readable on second phase of read')
                # if the input message ended, and nothing is to be read, an exception
                # will be raised, which we will catch.
                mesg = self._socket.recv(self.recvbufsize)
                if not mesg:
                    # if no exception is raised and an empty string has been read, it
                    # signifies that the connection has been broken.
                    raise ConnectionBrokenError(
                        'empty string read from socket: other end hung up.')
                logger.debug('Extending original message with: ' + str(mesg) + '; length: %d' %
                             len(mesg) + ' hex: ' + str(binascii.hexlify(mesg)))
                message = message + mesg
                if message.startswith(b'\0\0\0'):
                    raise ConnectionBrokenError(
                        'reading only null bytes from socket: probably we are talking to ser2net with no device attached to the serial port.')
        except InstrumentTimeoutError as ite:
            # this signifies the end of message, or a timeout when reading the first char.
            # In the former case, we simply ignore this condition. In the latter, we raise
            # an exception.
            if message is None:
                raise InstrumentError(
                    'Timeout while reading reply: ' + traceback.format_exc())
        except ConnectionBrokenError as cbe:
            # this is a serious error, we tear down the connection on our side.
            # We call the disconnecting method in this funny way, since it needs locking
            # self._socket_lock, which is now locked.
            logger.warning(
                'Connection to instrument broken. Trying to reconnect. Error was: ' + traceback.format_exc())
            GLib.idle_add(
                lambda: (self.disconnect_from_controller(False, reconnect=True) and False))
            raise cbe
        except socket.error as se:
            raise InstrumentError(
                'Communication Error: ' + traceback.format_exc())
        finally:
            self._socket.settimeout(self.timeout2)
        logger.debug('Returning with message: ' + str(message) + '; length: %d' %
                     len(message) + ' hex: ' + str(binascii.hexlify(message)))
        return message

    def send_and_receive(self, command, blocking=True):
        if isinstance(command, str):
            command = bytes(command, 'utf-8')
        with self._socketlock:
            try:
                self._socket.sendall(command)
                if not blocking:
                    return None
                if isinstance(blocking, float):
                    message = self._read_from_socket(blocking)
                else:
                    message = self._read_from_socket(None)
            except socket.error as err:
                raise InstrumentError(
                    'TCP socket I/O error: ' + traceback.format_exc())
            if (self._mesgseparator is not None) and message.endswith(self._mesgseparator):
                message = message[:-len(self._mesgseparator)]
            if (self._mesgseparator is not None) and self._mesgseparator in message:
                # if multiple messages received, only keep the first one which matches the current command,
                # if the list of the available commands (self._commands) is
                # defined (is not None)
                try:
                    cmd = self._get_command(command)
                    mymessage = [
                        m for m in message.split(self._mesgseparator) if cmd.match(m) is not None][0]
                    othermessages = [
                        m for m in message.split(self._mesgseparator) if m != mymessage]
                except (TypeError, IndexError, AttributeError):
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
        except queue.Empty:
            # this ensures that whenever the equipment gets disconnected, all the pending messages are processed before this
            # idle function is removed.
            return self.connected()
        except:
            logger.debug('Check_inqueue of instrument %s.' % self._name)
            print('--------- %s ------------' % self._name)
            raise
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
    # socket should have a reasonable timeout (e.g. 0.001, but not zero).

    def __init__(self, sock, parent, queue, lock, sleep=0.1, mesgseparator=None):
        self.socket = sock
        CommunicationCollector.__init__(
            self, parent, queue, lock, sleep, mesgseparator)

    def do_read(self):
        message = b''
        while True:
            rlist, wlist, xlist = select.select(
                [self.socket], [], [self.socket], 0.001)
            if xlist:
                raise ConnectionBrokenError('Socket in exceptional state')
            if not rlist:
                break
            try:
                mesg = self.socket.recv(1024)
            except (socket.timeout, socket.error):
                logger.warning(
                    'Socket error in CommunicationCollector: ' + traceback.format_exc())
                return message
            message += mesg
            if not mesg:
                # this signifies that the other end of the connection broke.
                raise ConnectionBrokenError(
                    'Empty message received, the other end of the connection broke.')
        if not message:
            # nothing has been read
            return None
        return message


class CommandReply(object):

    """This class implements a reply to a command. Each command can have multiple replies.
    Replies are parsed by default by regular expression matching, but this behaviour can
    be overridden by subclassing and modifying the match() method."""

    def __init__(self, regex, findall_regex=None, defaults=None):
        if not isinstance(regex, bytes):
            regex = bytes(regex, 'ascii')
        self.regex = re.compile(b'^' + regex + b'$', re.MULTILINE)
        if findall_regex is not None and isinstance(findall_regex, str):
            findall_regex = bytes(findall_regex, 'ascii')
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
        if not isinstance(command, bytes):
            command = bytes(command, 'ascii')
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
