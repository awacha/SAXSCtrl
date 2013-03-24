# -*- coding: utf-8 -*-
"""
Created on Tue Jan  8 14:36:06 2013

@author: labuser
"""

import socket
import re
import time
import select
import threading
import dateutil.parser
import uuid
import logging
import Queue
from gi.repository import GObject
import multiprocessing

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class PilatusError(StandardError):
    pass

class CommunicationError(PilatusError):
    pass

class TimeoutError(PilatusError):
    pass

class Message(object):
    def __init__(self, message, retries=0):
        if isinstance(message, Message):
            self.message = message.message
            self.retries = message.retries + 1
        else:
            self.message = message
            self.retries = 0
    def __cmp__(self, other):
        return cmp(other.retries, self.retries)
    def __str__(self):
        return self.message
    def __unicode__(self):
        return self.message

class PilatusCommand(object):
    _instances = []
    def __init__(self, cmd, context, regexes_dicts=None, argtypes=None):
        self.cmd = cmd
        self.context = context
        if regexes_dicts is None:
            self.regexes = None
            self.argtypes = (str,)
        else:
            self.regexes = {}
            for regex, dic in regexes_dicts:
                if isinstance(regex, basestring):
                    regex = re.compile(regex)
                self.regexes[regex] = dic
            if self.argtypes is None:
                raise ValueError('argument argtypes cannot be None if regexes is not None.')
            self.argtypes = tuple(argtypes[n] for n in sorted(argtypes.keys()))
        
        PilatusCommand._instances.append(self)
    @classmethod
    def get_instance(cls, cmdname):
        return [cmd for cmd in cls._instances if cmd.cmd.upper() == cmdname.upper()][0]
    @classmethod
    def get_instances(cls):
        return cls._instances[:]
    def get_gsignal(self):
        return ('camserver-' + self.cmd, (GObject.SignalFlags.RUN_FIRST, None, self.argtypes))
    def parse(self, context, status, mesg):
        if context != self.context:
            return None
        if self.regexes is None:
            gd = {self.cmd:mesg}
            return gd
        for regex in self.regexes:
            m = regex.match(mesg)
            if m is None:
                continue
            else:
                gd = self.regexes[regex].copy()
                gd.update(m.groupdict())
                for argname, argtype in zip(sorted(gd.keys()), self.argtypes):
                    gd[k] = argtype(gd[k])
                return gd
        return None
    def __del__(self):
        PilatusCommand._instances.remove(self)

PilatusCommand('Tau', 15, [('Set up rate correction: tau = (?P<tau>\d+(\.\d*)?(e[+-]?\d+)?) s', {'cutoff':None})
                           ('Turn off rate correction', {'tau':'0', 'cutoff':None})
                           ('Rate correction is on; tau = (?P<tau>\d+(\.\d*)?(e[+-]?\d+)?) s, cutoff = (?P<cutoff>\d+) counts', {})
                           ('Rate correction is off, cutoff = (?P<cutoff>\d+) counts', {'tau':'0'})],
               {'tau':float, 'cutoff':int})
PilatusCommand('ExpTime', 15, [('Exposure time set to: (?P<exptime>\d+\.\d+) sec.', {})], {'exptime':float})
PilatusCommand('Exposure', 15, [('Starting (?P<exptime>\d+\.\d+) second (?P<exptype>\w*?): (?P<expdatetime>\d{4,4}-\d{2,2}-\d{2,2}T\d{2,2}:\d{2,2}:\d{2,2}.\d+)', {})],
               {'exptime':float, 'exptype':str, 'expdatetime':str})
PilatusCommand('THread', 215, [('Channel (?P<channel>\d+): Temperature = (?P<temp>\d+\.\d+)C, Rel\. Humidity = (?P<humidity>\d+.\d+)%', {})],
               {'channel':int, 'temp':float, 'humidity':float})
PilatusCommand('ImgPath', 10, None)
PilatusCommand('ExpEnd', 6, None)
PilatusCommand('exposurefinished', 7, None)
PilatusCommand('Df', 5, None)
PilatusCommand('ImgMode', 15, [('ImgMode is (?P<imgmode>.*)', {})], {'imgmode':str})
PilatusCommand('SetThreshold', 15, [('/tmp/setthreshold.cmd', {'gain':None, 'threshold':None, 'vcmp':None, 'trimfile':None})
                                  ('Settings: (?P<gain>\w+) gain; threshold: (?P<threshold>\d+) eV; vcmp: (?P<vcmp>\d+(\.\d+)?) V\s*Trim file:\s*(?P<trimfile>.*)'), {}],
               {'gain':str, 'threshold':float, 'vcmp':float, 'trimfile':str})
PilatusCommand('ExpPeriod', 15, [('Exposure period set to: (?P<expperiod>\d+.\d+) sec', {})],
               {'expperiod':float})
PilatusCommand('NImages', 15, [('N images set to: (?P<nimages>\d+)', {})], {'nimages':float})
PilatusCommand('SetAckInt', 15, [('Acknowledgement interval is (?P<ackint>\d+)', {})], {'ackint':int})
PilatusCommand('K', 13, None)
PilatusCommand('Send', 15, None)
PilatusCommand('Exit', 1000, None)
# TODO:  regex for camsetup command
PilatusCommand('CamSetup', 2, None)

class PilatusCommProcess(multiprocessing.Process):
    _eventnames = ['tau', 'getthreshold', 'setackint', 'expperiod', 'nimages', 'disconnect_from_camserver', 'imgmode', 'setthreshold', 'mxsettings', 'camsetup', 'exptime', 'OK', 'exposure', 'expend', 'exposure_finished', 'imgpath', 'df', 'thread']
    iotimeout = 0.1
    mesglen = 1024
    def __init__(self, host, port=41234, name=None, group=None):
        multiprocessing.Process.__init__(self, name=name, group=group)
        self.inqueue = multiprocessing.Queue()
        self.outqueue = multiprocessing.Queue()
        self.killswitch = multiprocessing.Event()
        self.conditions = {}
        self._commands = PilatusCommand.get_instances()
        self.sendqueue2 = Queue.PriorityQueue()
        for c in self._commands:
            self.conditions[c.cmd] = multiprocessing.Condition(lock)
        self.socket = None
        self.pilatus_lock = multiprocessing.Lock()
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ip = socket.gethostbyname(host)
            self.socket.connect((ip, port))
            self.host = host
            self.port = port
        except socket.gaierror:
            self.socket = None
            raise PilatusError('Cannot resolve host name.')
        except socket.error:
            self.socket = None
            raise PilatusError('Cannot connect to camserver.')
        logger.debug('Connected to server %s:%d' % (host, port))
    def handle_event(self, contextnumber, status, mesg):
        dic = None
        for c in self._commands:
            dic = c.parse(contextnumber, status, mesg)
            if dic is None:
                continue
        if dic is None:
            logger.error('Unknown camserver command for message: ', message)
            return
        self.outqueue.put((c.cmd, status, dic))
        self.conditions[c.cmd].acquire()
        self.conditions[c.cmd].notify_all()
        self.conditions[c.cmd].release()
    def disconnect_from_camserver(self):
        if self.socket is None:
            raise PilatusError('Cannot disconnect: connection is already closed.')
        self.killswitch.set()
        self.join()
    def __del__(self):
        try:
            self.disconnect_from_camserver()
        except PilatusError:
            pass
    def _process_sending(self):
        while True:
            # move the incoming messages to send to the priority queue. They will be processed
            # from there. This is needed, since multiprocessing.queues.Queue does not
            # handle priorities, which we need in case of unwritable sockets.
            try:
                msgtosend = self.inqueue.get_nowait()
                self.sendqueue2.put(Message(msgtosend))
            except multiprocessing.queues.Empty:
                # if no messages, break the loop.
                msgtosend = None
        try:
            msgtosend = self.sendqueue2.get_nowait()
        except Queue.Empty:
            return
        while msgtosend is not None:
            # find the preferred socket for the message.
            with self.pilatus_lock:
                writable, exceptional = select.select([], [self.socket], [self.socket], self.iotimeout)[1:3]
            if exceptional:
                raise CommunicationError('Exceptional state on send')
            if not writable:
                # put the message back to the priority queue, with an increased priority
                self.sendqueue2.put(Message(msgtosend))
                return
            # if we have a writable socket to send our message to, separate the command part and check if we have a corresponding event.
            cmd = str(msgtosend).strip().split()[0]
            try:
                # add a whitespace to the end. This is needed because of a bug in camserver
                mesg1 = str(msgtosend) + ' '
                chars_sent = 0
                while chars_sent < len(mesg1):
                    chars_sent += sock.send(mesg1[chars_sent:])
                logger.debug('Sent to camserver:' + str(msgtosend))
            except socket.error:
                raise CommunicationError('Socket error on send')
            # get the next message
            try:
                msgtosend = self.sendqueue2.get_nowait()
            except Queue.Empty:
                return
    def _process_receiving(self):
        with self.pilatus_lock:
            readable, exceptional = select.select([self.socket], [self.socket], [self.socket], self.iotimeout)[0:3:2]
            if exceptional:
                raise CommunicationError('Exceptional state on read')
            mesg = ''
            while readable:
                newmesg = self.socket.recv(self.mesglen)
                if not newmesg:  # was readable but 0 bytes received: socket closed.
                    raise CommunicationError('Socket closed by camserver')
                mesg = mesg + newmesg
                readable = select.select([self.socket], [self.socket], [self.socket], 0)[0:3:2]
                if exceptional:
                    raise CommunicationError('Exceptional state on read')
        logging.debug('Read from camserver: ' + mesg)
        # handle all nonempty messages.
        for msg in [m for m in mesg.split('\x18') if m]:
            try:
                # split event message into parts
                data = re.match('^(?P<context>\d+)\s+(?P<state>\w+)\s*(?P<message>.*)', msg, re.DOTALL | re.MULTILINE).groupdict()                   
                contextnumber = int(data['context'])
                state = data['state']
                message = data['message']
            except AttributeError:  # raised if the regular exception does not match
                raise PilatusError('Invalid message received: ' + msg)
            except ValueError:  # raised if the contextnumber is not a number.
                raise PilatusError('Invalid context number in message: ' + msg)
            if state not in [ 'ERR', 'OK']:
                raise PilatusError('Invalid status in message: ' + msg)
            if state == 'ERR':
                logger.error('Camserver: ' + msg)
            self.handle_event(contextnumber, state, message)
    def run(self):
        # this function constitutes of a main loop, which can be ended via a ''poison-pill'' mechanism.
        try:
            while not self.killswitch.is_set():
                # first try to send, if there are messages to send.
                self._process_sending()
                self._process_receiving()
        except CommunicationError,commerr:
            logger.critical('Socket exception: '+commerr.message)
            mesg = '1000 ERR socket closed: ' + commerr.message
        else:
            logger.debug('Socket closed normally.')
            mesg='1000 OK socket closed normally.'
        finally:
            self.socket.close()
            self.socket = None
            self.handle_event(mesg)

class PilatusConnection(GObject.GObject):
    __gsignals__ = dict([c.get_gsignal() for c in PilatusCommand.get_instances()]) 
    _status = {}
    _status_timeout = 0.1
    _status_time = None
    _timeout_handler = None
    def __init__(self, host='localhost', port=41234):
        self.host = host
        self.port = port
        self.commprocess = None
        if host is not None:
            self.connect_to_camserver()
    def poll_commqueue(self):
        try:
            cmd, status, dic = self.commprocess.outqueue.get_nowait()
        except multiprocessing.queues.Empty:
            return True
        self.emit('camserver-' + cmd, status, *[dic[k] for k in sorted(dic.keys())])
        return True
    def do_camserver_Exit(self, pilatusconnection, status, message):
        self.disconnect_from_camserver()
    def connect_to_camserver(self):
        self.commprocess = PilatusCommProcess(self.host, self.port)
        self.commprocess.daemon = True
        self.idle_function_handle = GObject.idle_add(self.poll_commqueue)
        self.commprocess.start()
    def reconnect_to_camserver(self):
        self.disconnect_from_camserver()
        self.connect_to_camserver()
    def disconnect_from_camserver(self):
        GObject.source_remove(self.idle_function_handle)
        self.commprocess.disconnect_from_camserver()
        self.commprocess.join()
        self.commprocess = None
    def connected(self):
        """Return if connected to camserver"""
        return self.commprocess is not None
    def _interpret_message(self, contextnumber, status, message):
        """Interpret the received message"""
        message = message.strip()
        if contextnumber == 2 and message.startswith('Camera definition:'):
            for l in [x.strip() for x in message.split('\n')]:
                if l.startswith('Camera name:'):
                    self._status['camname'] = l.split(':')[1].strip()
                if l.startswith('Camera state:'):
                    self._status['state'] = l.split(':')[1].strip()
                if l.startswith('Target file:'):
                    targetfile = l.split(':')[1].strip()
                    if targetfile == '(nil)':
                        targetfile = None
                    self._status['targetfile'] = targetfile
                if l.startswith('Time left:'):
                    self._status['timeleft'] = float(l.split(':')[1].strip())
                if l.startswith('Exposure time:'):
                    self._status['exptime'] = float(l.split(':')[1].strip())
            self._status_time = time.time()
            self.events['camsetup'][1] = self._status
            self._call_handlers('camsetup')
            self.events['camsetup'][0].set()
        elif contextnumber == 15 and message.startswith('Command:'):
            # using the demo P6M detector some commands are not implemented.
            cmd = message[8:].strip().split(None, 1)[0]
            if cmd.lower() in self.events:
                self.events[cmd.lower()][0].set()
            elif cmd.lower() in ['fillpix', 'calibrate']:
                self.events['OK'][0].set()
        elif contextnumber == 6:
            self.events['expend'][1] = message
            self._call_handlers('expend')
            self.events['expend'][0].set()
        elif contextnumber == 15 and re.search('Starting \d+\.\d+ second', message) is not None:
            m = re.search('Starting (?P<exptime>\d+\.\d+) second (?P<exptype>\w*?): (?P<expdatetime>\d{4,4}-\d{2,2}-\d{2,2}T\d{2,2}:\d{2,2}:\d{2,2}.\d+)', message)
            if m is not None:
                self.events['exposure'][1] = m.groupdict()
                self.events['exposure'][1]['exptime'] = float(self.events['exposure'][1]['exptime'])
                self.events['exposure'][1]['expdatetime'] = dateutil.parser.parse(self.events['exposure'][1]['expdatetime'])
            self._expstarted = time.time()
            self._call_handlers('exposure')
            self.events['exposure_finished'][0].clear()
            self.events['exposure'][0].set()
        elif contextnumber == 7:
            self.events['exposure_finished'][1] = message
            self.events['exposure_finished'][2] = status
            self._call_handlers('exposure_finished')
            self.events['exposure_finished'][0].set()
        elif contextnumber == 215:  # temperature and humidity
            matches = re.findall('Channel (?P<channel>\d+): Temperature = (?P<temp>\d+\.\d+)C, Rel\. Humidity = (?P<humidity>\d+.\d+)%', message)
            self.events['thread'][1] = []
            for m in matches:
                self.events['thread'][1].append({'Channel':int(m[0]), 'Temp':float(m[1]), 'Humidity':float(m[2])})
            self._call_handlers('thread')
            self.events['thread'][0].set()
        elif contextnumber == 10:  # image path
            self.events['imgpath'][1] = message
            self._call_handlers('imgpath')
            self.events['imgpath'][0].set()
        elif contextnumber == 5:  # df
            self.events['df'][1] = int(message)
            self._call_handlers('df')
            self.events['df'][0].set()
        elif contextnumber == 15 and message.startswith('ImgMode is '):
            self.events['imgmode'][1] = message.rsplit(" ", 1)[1]
            self._call_handlers('imgmode')
            self.events['imgmode'][0].set()
        elif contextnumber == 15 and message == '/tmp/setthreshold.cmd':
            self.events['setthreshold'][1] = message
            self._call_handlers('setthreshold')
            self.events['setthreshold'][0].set()
        elif contextnumber == 15 and message.startswith('Exposure period set to:'):
            self.events['expperiod'][1] = float(message[len('Exposure period set to:'):].split()[0])
            self._call_handlers('expperiod')
            self.events['expperiod'][0].set()
        elif contextnumber == 15 and message.startswith('N images set to:'):
            self.events['nimages'][1] = int(message[len('N images set to:'):])
            self._call_handlers('nimages')
            self.events['nimages'][0].set()
        elif contextnumber == 15 and message.startswith('Acknowledgement interval is'):
            self.events['setackint'][1] = int(message[len('Acknowledgement interval is'):].strip())
            self._call_handlers('setackint')
            self.events['setackint'][0].set()
        elif contextnumber == 15 and message.startswith('Set up rate correction'):
            m = re.match('Set up rate correction: tau = (?P<tau>\d+(\.\d*)?(e[+-]?\d+)?) s', message)
            m = m.groupdict()
            m['tau'] = float(m['tau'])
            self.events['tau'][1] = m
            self._call_handlers('tau')
            self.events['tau'][0].set()
        elif contextnumber == 15 and message.startswith('Turn off rate correction'):
            self.events['tau'][1] = {'tau':0}
            self._call_handlers('tau')
            self.events['tau'][0].set()
        elif contextnumber == 15 and message.startswith('Rate correction'):
            m = re.match('Rate correction is on; tau = (?P<tau>\d+(\.\d*)?(e[+-]?\d+)?) s, cutoff = (?P<cutoff>\d+) counts', message)
            if m is None:
                m = re.match('Rate correction is off, cutoff = (?P<cutoff>\d+) counts', message)
            m = m.groupdict()
            if 'tau' not in m:
                m['tau'] = 0
            m['tau'] = float(m['tau'])
            m['cutoff'] = float(m['cutoff'])
            self.events['tau'][1] = m
            self._call_handlers('tau')
            self.events['tau'][0].set()
        elif contextnumber == 15 and message.startswith('Settings: '):
            m = re.match('Settings: (?P<gain>\w+) gain; threshold: (?P<threshold>\d+) eV; vcmp: (?P<vcmp>\d+(\.\d+)?) V\s*Trim file:\s*(?P<trimfile>.*)', message)
            if m is None:
                raise CommunicationError()
            m = m.groupdict()
            m['gain'] = m['gain'] + 'G'
            m['threshold'] = int(m['threshold'])
            m['vcmp'] = float(m['vcmp'])
            self.events['getthreshold'][1] = m
            self._call_handlers('getthreshold')
            self.events['getthreshold'][0].set()
        elif contextnumber == 15:
            # just a simple OK message
            self._call_handlers('OK')
            self.events['OK'][0].set()
        elif contextnumber == 13:
            self.events['exposure_finished'][1] = message
            self.events['exposure_finished'][2] = status
            self._call_handlers('exposure_finished')
            self.events['exposure_finished'][0].set()
        else:
            logger.warn("Unknown but valid message: " + str(contextnumber) + ' ' + status + ' ' + message)
    def _comm_worker(self):
        """worker function for the receiving thread. This is responsible for all the communication over TCP/IP between
        camserver and this class."""
        
    def _call_handlers(self, eventname):
        for uuid in self.events[eventname][3]:
            self.events[eventname][3][uuid](self.events[eventname][1], self.events[eventname][2])
    def send(self, mesg):
        if not self.connected():
            raise CommunicationError('Socket closed')
        logger.debug('sending message: ' + mesg)
        self.commprocess.inqueue.put(mesg)
    def get_status(self, force=False):
        if self._status_time is not None and (time.time() - self._status_time) < self._status_timeout and not force:
            return self._status
        else:
            self.send('camsetup')
            return self.wait_for_event('camsetup')[0]
    def setackint(self, ackint=0):
        self.send('setackint %d' % ackint)
        ackintset = self.wait_for_event('setackint')[0]
        if acintset != acint:
            raise ValueError('Error setting acknowledgement interval!')
        return ackintset
    def expose(self, exptime, filename, Nimages=1, expdwelltime=0.003):
        self.send('exptime %f' % exptime)
        exptimeset = self.wait_for_event('exptime')[0]
        if abs(float(exptimeset) - exptime) > 1e-5:
            raise ValueError('Error setting exposure time!')
        self.send('nimages %d' % Nimages)
        nimagesset = self.wait_for_event('nimages')[0]
        if nimagesset != Nimages:
            raise ValueError('Error setting number of images to %d!' % Nimages)
        self.send('expperiod %f' % (exptime + expdwelltime))
        expperiodset = self.wait_for_event('expperiod')[0]
        if abs(expperiodset - exptime - expdwelltime) > 1e-5:
            raise ValueError('Error setting exposure period!')
        self.send('exposure %s' % filename)
        if Nimages == 1:
            logger.debug('Starting %f seconds exposure to filename %s.' % (exptime, filename))
        else:
            logger.debug('Starting %d exposures. Exptime: %f seconds. Period: %f seconds. Starting file: %s' % (Nimages, exptime, exptime + expdwelltime, filename))
        return self.wait_for_event('exposure')[0]
    def wait_for_event(self, name, timeout=1):
        logger.debug('Waiting for event: ' + name)
        self.events[name][0].wait(timeout)
        if not self.events[name][0].isSet():
            logger.debug('Event timeout: ' + name)
            raise TimeoutError(name)
        logger.debug('Event set: ' + name)
        data = (self.events[name][1], self.events[name][2])
        self.events[name][0].clear()
        return data
    def register_event_handler(self, eventname, callback):
        u = uuid.uuid1()
        self.events[eventname][3][u] = callback
        return u
    def unregister_event_handler(self, eventname, u):
        if u in self.events[eventname][3]:
            del self.events[eventname][3][u]
            return True
        else:
            return False
    def stopexposure(self):
        logger.debug('Stopping running exposure.')
        self.send('k')
        # we do not wait_for_event() here, because another thread may be doing the same.
        return
    @property
    def camname(self):
        return self.get_status()['camname']
    @property
    def camstate(self):
        return self.get_status()['state']
    @property
    def targetfile(self):
        return self.get_status()['targetfile']
    @property
    def timeleft(self):
        return self.get_status()['timeleft']
    @property
    def exptime(self):
        return self.get_status()['exptime']
    @property
    def percentdone(self):
        st = self.get_status()
        return (st['exptime'] - st['timeleft']) / st['exptime'] * 100
    @property
    def imgpath(self):
        self.send('imgpath')
        return self.wait_for_event('imgpath')[0]
    @imgpath.setter
    def imgpath(self, newpath):
        self.send('imgpath ' + newpath)
        data = self.wait_for_event('imgpath')[0]
        if data != newpath:
            raise PilatusError('Cannot set imgpath!')
        return data
    @property
    def df(self):
        self.send('df')
        return self.wait_for_event('df')[0]
    def temphum(self, channel=None):
        if channel is None:
            self.send('thread')
            data = self.wait_for_event('thread')[0]
            return data
        else:
            self.send('thread %d' % channel)
            data = self.wait_for_event('thread')[0]
            return (data[0]['Temp'], data[0]['Humidity'])
    def setthreshold(self, threshold, gain):
        logger.debug('Setting threshold to %d eV (gain: %s)' % (threshold, gain))
        self.send('setthreshold %s %d' % (gain, threshold))
        data = self.wait_for_event('setthreshold', 60)[0]
        return data
    def rbd(self):
        logger.debug('Read-back-detector starting...')
        self.send('imgmode p')
        self.wait_for_event('OK')
        self.send('fillpix 0x9d367')
        self.wait_for_event('OK')
        self.wait_for_idle()
        logger.debug('Read-back-detector finished.')
    def calibrate(self):
        logger.debug('Calibration started...')
        self.send('imgmode p')
        self.wait_for_event('OK')
        self.send('calibrate')
        self.wait_for_event('OK')
        self.wait_for_idle()
        logger.debug('Calibration finished.')
    def getthreshold(self):
        self.send('setthreshold')
        return self.wait_for_event('getthreshold')[0]
    def wait_for_idle(self, timeout=1):
        while self.camstate != 'idle':
            time.sleep(timeout)
    @property
    def imgmode(self):
        self.send('imgmode')
        return self.wait_for_event('imgmode')[0]
    @property
    def tau(self):
        self.send('tau')
        return self.wait_for_event('tau')[0]
    @tau.setter
    def tau(self, value):
        self.send('tau %g' % value)
        return self.wait_for_event('tau')[0]
