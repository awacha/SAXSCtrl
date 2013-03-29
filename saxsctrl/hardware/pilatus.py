# -*- coding: utf-8 -*-
"""
Created on Tue Jan  8 14:36:06 2013

@author: labuser
"""

import socket
import re
import os
import time
import select
import threading
import dateutil.parser
import uuid
import logging
import Queue
from gi.repository import GObject
from gi.repository import Gtk
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
            if argtypes is None:
                self.argtypes = (str,)
            else:
                self.argtypes = (argtypes,)
        else:
            self.regexes = {}
            for regex, dic in regexes_dicts:
                if isinstance(regex, basestring):
                    regex = re.compile(regex)
                self.regexes[regex] = dic
            if argtypes is None:
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
        return ('camserver-' + self.cmd, (GObject.SignalFlags.RUN_FIRST, None, (str,) + self.argtypes))
    def parse(self, context, status, mesg):
        if context != self.context:
            return
        if self.regexes is None:
            gd = {self.cmd:self.argtypes[0](mesg)}
            logger.debug('Matched command ' + self.cmd + ' based on context number alone.')
            yield gd
            return
        for regex in self.regexes:
            for m in regex.finditer(mesg):
                gd = self.regexes[regex].copy()
                gd.update(m.groupdict())
                for argname, argtype in zip(sorted(gd.keys()), self.argtypes):
                    gd[argname] = argtype(gd[argname])
                logger.debug('Matched command ' + self.cmd + ' based on regexp.')
                yield gd
        return
    def __del__(self):
        PilatusCommand._instances.remove(self)

PilatusCommand('Tau', 15, [('Set up rate correction: tau = (?P<tau>\d+(\.\d*)?(e[+-]?\d+)?) s', {'cutoff':0}),
                           ('Turn off rate correction', {'tau':'0', 'cutoff':0}),
                           ('Rate correction is on; tau = (?P<tau>\d+(\.\d*)?(e[+-]?\d+)?) s, cutoff = (?P<cutoff>\d+) counts', {}),
                           ('Rate correction is off, cutoff = (?P<cutoff>\d+) counts', {'tau':'0'})],
               {'tau':float, 'cutoff':int})
PilatusCommand('ExpTime', 15, [('Exposure time set to: (?P<exptime>\d+\.\d+) sec.', {})], {'exptime':float})
PilatusCommand('Exposure', 15, [('Starting (?P<exptime>\d+\.\d+) second (?P<exptype>\w*?): (?P<expdatetime>\d{4,4}-\d{2,2}-\d{2,2}T\d{2,2}:\d{2,2}:\d{2,2}.\d+)', {})],
               {'exptime':float, 'exptype':str, 'expdatetime':str})
PilatusCommand('THread', 215, [('Channel (?P<channel>\d+): Temperature = (?P<temp>\d+\.\d+)C, Rel\. Humidity = (?P<humidity>\d+.\d+)%', {}),
                               ('Channel (?P<channel>\d+) is not implemented', {'temp':0, 'humidity':0})],
               {'channel':int, 'temp':float, 'humidity':float})
PilatusCommand('ImgPath', 10, None)
PilatusCommand('ExpEnd', 6, None)
PilatusCommand('exposurefinished', 7, None)
PilatusCommand('Df', 5, None, int)
PilatusCommand('ImgMode', 15, [('ImgMode is (?P<imgmode>.*)', {})], {'imgmode':str})
PilatusCommand('SetThreshold', 15, [('/tmp/setthreshold.cmd', {'gain':'(nil)', 'threshold':0, 'vcmp':0, 'trimfile':'(nil)'}),
                                  ('Settings: (?P<gain>\w+) gain; threshold: (?P<threshold>\d+) eV; vcmp: (?P<vcmp>\d+(\.\d+)?) V\s*Trim file:\s*(?P<trimfile>.*)', {})],
               {'gain':str, 'threshold':float, 'vcmp':float, 'trimfile':str})
PilatusCommand('ExpPeriod', 15, [('Exposure period set to: (?P<expperiod>\d+.\d+) sec', {})],
               {'expperiod':float})
PilatusCommand('NImages', 15, [('N images set to: (?P<nimages>\d+)', {})], {'nimages':float})
PilatusCommand('SetAckInt', 15, [('Acknowledgement interval is (?P<ackint>\d+)', {})], {'ackint':int})
PilatusCommand('K', 13, None)
PilatusCommand('Send', 15, None)
PilatusCommand('Exit', 1000, None)
PilatusCommand('CamSetup', 2, [("\s*Camera definition:\n\s+(?P<cameradef>.*)\n\s*Camera name: (?P<cameraname>.*),\sS/N\s(?P<cameraSN>\d+-\d+)\n\s*Camera state: (?P<camstate>.*)\n\s*Target file: (?P<targetfile>.*)\n\s*Time left: (?P<timeleft>\d+(\.\d+)?)\n\s*Last image: (?P<lastimage>.*)\n\s*Master PID is: (?P<masterPID>\d+)\n\s*Controlling PID is: (?P<controllingPID>\d+)\n\s*Exposure time: (?P<exptime>\d+(\.\d+)?)\n\s*Last completed image:\s*\n\s*(?P<lastcompletedimage>.*)\n\s*Shutter is: (?P<shutterstate>.*)\n", {})],
               {'cameradef':str, 'cameraname':str, 'cameraSN':str, 'camstate':str, 'targetfile':str, 'timeleft':float,
                'lastimage':str, 'masterPID':int, 'controllingPID':int, 'exptime':float, 'lastcompletedimage':str, 'shutterstate':str})
                               

class PilatusCommProcess(multiprocessing.Process):
    iotimeout = 0.1
    mesglen = 20
    def __init__(self, host, port=41234, name=None, group=None):
        multiprocessing.Process.__init__(self, name=name, group=group)
        self.inqueue = multiprocessing.Queue()
        self.outqueue = multiprocessing.Queue()
        self.killswitch = multiprocessing.Event()
        self.conditions = {}
        self._commands = PilatusCommand.get_instances()
        self.sendqueue2 = Queue.PriorityQueue()
        for c in self._commands:
            self.conditions[c.cmd] = multiprocessing.Condition()
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
    def handle_event(self, contextnumber, status, mesg, epoch):
        logger.debug('Handling event in comm process. Context: ' + str(contextnumber) + '; Status: ' + status + '; Message: ' + mesg)
        dic = None
        for c in self._commands:
            for dic in c.parse(contextnumber, status, mesg):
                found = True
                self.outqueue.put((c.cmd, status, dic, epoch, mesg))
            if dic is not None:
                break
        if dic is None:
            logger.error('Unknown camserver command for message: ' + mesg)
            return
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
                break
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
                mesg1 = str(msgtosend)
                # pad the message to the last used message length to work around a bug in camserver, which does not erase the last input string buffer.
                mesg1 = mesg1 + ' ' * (self.mesglen - len(mesg1))
                self.mesglen = len(mesg1)
                chars_sent = 0
                while chars_sent < len(mesg1):
                    chars_sent += self.socket.send(mesg1[chars_sent:])
                logger.debug('Sent to camserver:' + str(msgtosend))
            except socket.error:
                raise CommunicationError('Socket error on send')
            # get the next message
            try:
                msgtosend = self.sendqueue2.get_nowait()
            except Queue.Empty:
                return
    def _process_receiving(self):
        mesg = []
        with self.pilatus_lock:
            readable, exceptional = select.select([self.socket], [self.socket], [self.socket], self.iotimeout)[0:3:2]
            if exceptional:
                raise CommunicationError('Exceptional state on read')
            while readable:
                newmesg = self.socket.recv(self.mesglen)
                if not newmesg:  # was readable but 0 bytes received: socket closed.
                    raise CommunicationError('Socket closed by camserver')
                mesg.append(newmesg)
                readable, exceptional = select.select([self.socket], [self.socket], [self.socket], 0)[0:3:2]
                if exceptional:
                    raise CommunicationError('Exceptional state on read')
        if mesg:
            mesg = ''.join(mesg)
            logger.debug('Read from camserver: ' + mesg)
        else:
            return
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
            self.handle_event(contextnumber, state, message, time.time())
    def run(self):
        logging.debug('Starting main communication loop.')
        # this function constitutes of a main loop, which can be ended via a ''poison-pill'' mechanism.
        try:
            while not self.killswitch.is_set():
                # first try to send, if there are messages to send.
                self._process_sending()
                self._process_receiving()
        except CommunicationError, commerr:
            logger.critical('Socket exception: ' + commerr.message)
            mesg = 'socket closed: ' + commerr.message
            state = 'ERR'
        except Exception, ex:
            mesg = 'Other exception: ' + ex.message
            state = 'ERR' 
        else:
            logger.debug('Socket closed normally.')
            mesg = 'socket closed normally.'
            state = 'OK'
        finally:
            self.socket.close()
            self.socket = None
            self.handle_event(1000, state, mesg, time.time())
            logging.debug('Ending main communication loop.')

def add_dicts(d1, d2):
    """Summarize two dicts d1 and d2. Keys of d2 should be valid (and defined)
    in d1 as well. Note that not all values in d2 should be lists.
    
    Inputs: d1:
    """
    if not all(isinstance(d1[k], list) for k in d1):
        d11 = {k:[d1[k]] for k in d1}
        d1 = d11
    sumd = {k:d1[k] + [d2[k]] for k in d2}
    return sumd
            
class PilatusConnection(GObject.GObject):
    __gsignals__ = dict([c.get_gsignal() for c in PilatusCommand.get_instances()] + [('camserver-error', (GObject.SignalFlags.RUN_FIRST, None, (str,))),
                                                                                     ('connect-camserver', (GObject.SignalFlags.RUN_FIRST, None, ())),
                                                                                     ('disconnect-camserver', (GObject.SignalFlags.RUN_FIRST, None, ()))])
    _uninterruptible = 0
    lastresults = None
    camserver_reply_timeout = 0.3
    idle_function_handle = None
    def __init__(self, host='localhost', port=41234):
        GObject.GObject.__init__(self)
        self.host = host
        self.port = port
        self.commprocess = None
        if host is not None:
            self.connect_to_camserver()
    def poll_commqueue(self, blocking=False, timeout=0.3):
        if not self.connected(): raise PilatusError('Not connected to camserver.')
        handled = []
        while True:
            try:
                cmd, status, dic, epoch, message = self.commprocess.outqueue.get(blocking, timeout)
            except multiprocessing.queues.Empty:
                break
            if self.lastresults[cmd][0] != epoch:
                self.lastresults[cmd] = (epoch, status, dic)
            else:
                self.lastresults[cmd] = (epoch, status, add_dicts(self.lastresults[cmd][2], dic))
            handled.append(cmd)
            self.emit('camserver-' + cmd, status, *[dic[k] for k in sorted(dic.keys())])
            if status == 'ERR':
                self.emit('camserver-error', message)
        return len(handled)
    def do_camserver_Exit(self, status, message):
        self.disconnect_from_camserver()
    def connect_to_camserver(self):
        if self.connected():
            raise PilatusError('Already connected')
        self.lastresults = {}
        for c in PilatusCommand.get_instances():
            self.lastresults[c.cmd] = (None, None, {})
        self.commprocess = PilatusCommProcess(self.host, self.port)
        self.commprocess.daemon = True
        def _handler():
            self.poll_commqueue(blocking=False)
            return True
        self.idle_function_handle = GObject.idle_add(_handler)
        self.commprocess.start()
        self.emit('connect-camserver')
    def reconnect_to_camserver(self):
        self.disconnect_from_camserver()
        self.connect_to_camserver()
    def disconnect_from_camserver(self):
        if not self.connected():
            raise PilatusError('Not connected')
        GObject.source_remove(self.idle_function_handle)
        self.commprocess.disconnect_from_camserver()
        self.commprocess.join()
        self.commprocess = None
        self.emit('disconnect-camserver')
    def connected(self):
        """Return if connected to camserver"""
        return self.commprocess is not None
    def send(self, mesg):
        if not self.connected():
            raise PilatusError('Not connected')
        logger.debug('sending message: ' + mesg)
        self.commprocess.inqueue.put(mesg)
    def get_status(self, age_tolerance=1):
        if self.lastresults['CamSetup'][0] is not None and (time.time() - self.lastresults['CamSetup'][0]) < age_tolerance:
            logger.debug('Re-using last result.')
            return self.lastresults['CamSetup'][2]
        else:
            with self.reset_and_wait_for_event(self, 'CamSetup'):
                self.send('CamSetup')
            return self.lastresults['CamSetup'][2]
    def setackint(self, ackint=0):
        with self.reset_and_wait_for_event(self, 'Send'):
            self.send('SetAckInt %d' % ackint)
    def getackint(self):
        with self.reset_and_wait_for_event(self, 'SetAckInt'):
            self.send('SetAckInt')
        return self.lastresults['SetAckInt'][2]['ackint']
    def expose(self, exptime, filename, Nimages=1, expdwelltime=0.003):
        with self.reset_and_wait_for_event(self, 'ExpTime', timeout=1):
            self.send('ExpTime %f' % exptime)
        exptimeset = self.lastresults['ExpTime'][2]['exptime']
        if abs(float(exptimeset) - exptime) > 1e-5:
            raise ValueError('Error setting exposure time!')
        with self.reset_and_wait_for_event(self, 'NImages'):
            self.send('NImages %d' % Nimages)
        nimagesset = self.lastresults['NImages'][2]['nimages']
        if nimagesset != Nimages:
            raise ValueError('Error setting number of images to %d!' % Nimages)
        with self.reset_and_wait_for_event(self, 'ExpPeriod'):
            self.send('ExpPeriod %f' % (exptime + expdwelltime))
        expperiodset = self.lastresults['ExpPeriod'][2]['expperiod']
        if abs(expperiodset - exptime - expdwelltime) > 1e-5:
            raise ValueError('Error setting exposure period!')
        with self.reset_and_wait_for_event(self, 'Exposure'):
            self.send('Exposure %s' % filename)
        if Nimages == 1:
            logger.debug('Starting %f seconds exposure to filename %s.' % (exptime, filename))
        else:
            logger.debug('Starting %d exposures. Exptime: %f seconds. Period: %f seconds. Starting file: %s' % (Nimages, exptime, exptime + expdwelltime, filename))
        return self.lastresults['Exposure'][2]
    def get_last_results(self, commandname):
        return self.lastresults[commandname]
    class reset_and_wait_for_event(object):
        def __init__(self, pconnection, commandname, timeout=None):
            self.pconnection = pconnection
            if isinstance(commandname, basestring):
                commandname = [commandname]
            self.commandnames = commandname
            if timeout is None:
                timeout = pconnection.camserver_reply_timeout
            self.timeout = timeout
        def __enter__(self):
            logger.debug('Resetting last results for command(s): ' + str(self.commandnames))
            for cn in self.commandnames:
                self.pconnection.lastresults[cn] = (None, None, None)
        def __exit__(self, *args, **kwargs):
            logger.debug('Starting waiting loop for command(s): ' + str(self.commandnames))
            self.pconnection.poll_commqueue()  # empty the queue if there are pending events
            time0 = time.time()
            while all(self.pconnection.lastresults[cmdname][0] is None for cmdname in self.commandnames) and time.time() - time0 <= self.timeout:  # if the result is still not there, give it one more try.
                self.pconnection.poll_commqueue(blocking=True)
            if all(self.pconnection.lastresults[cmdname][0] is None for cmdname in self.commandnames):
                raise TimeoutError
            if any([self.pconnection.lastresults[c][1] == 'ERR' for c in self.commandnames if self.pconnection.lastresults[c][0] is not None]):
                raise PilatusError('Camserver returned status ERR.')
    def stopexposure(self):
        logger.debug('Stopping running exposure.')
        self.send('k')
        # we do not wait_for_event() here, because another thread may be doing the same.
        return
    @GObject.property
    def camname(self):
        return self.get_status()['cameraname']
    @GObject.property
    def camstate(self):
        if not self.connected():
            return 'disconnected'
        return self.get_status()['camstate']
    @GObject.property
    def targetfile(self):
        return self.get_status()['targetfile']
    @GObject.property
    def timeleft(self):
        return self.get_status()['timeleft']
    @GObject.property
    def exptime(self):
        return self.get_status()['exptime']
    @exptime.setter
    def exptime(self, exptime):
        with self.reset_and_wait_for_event(self, 'ExpTime', timeout=1):
            self.send('ExpTime %f' % exptime)
    @GObject.property
    def percentdone(self):
        st = self.get_status()
        return (st['exptime'] - st['timeleft']) / st['exptime'] * 100
    @GObject.property
    def imgpath(self):
        with self.reset_and_wait_for_event(self, 'ImgPath'):
            self.send('ImgPath')
        return self.lastresults['ImgPath'][2]['ImgPath']
    @imgpath.setter
    def imgpath(self, newpath):
        with self.reset_and_wait_for_event(self, 'ImgPath'):
            self.send('ImgPath ' + newpath)
        data = self.lastresults['ImgPath'][2]['ImgPath']
        return data
    @GObject.property
    def df(self):
        with self.reset_and_wait_for_event(self, 'Df'):
            self.send('Df')
        return self.lastresults['Df'][2]['Df']
    def temphum(self, channel=None):
        if channel is None:
            cmd = 'THread'
        else:
            cmd = 'THread %d' % channel
        with self.reset_and_wait_for_event(self, 'THread'):
            self.send(cmd)
        data = self.lastresults['THread'][2]
        return data
    def setthreshold(self, threshold, gain, blocking=True):
        logger.debug('Setting threshold to %d eV (gain: %s)' % (threshold, gain))
        if blocking:
            with self.reset_and_wait_for_event(self, 'SetThreshold', timeout=60):
                self.send('SetThreshold %s %d' % (gain, threshold))
            return self.lastresults['SetThreshold'][2]
        else:
            self.send('SetThreshold %s %d' % (gain, threshold))
    def rbd(self, outputfile=None):
        logger.debug('Read-back-detector starting...')
        with self.reset_and_wait_for_event(self, 'Send'):
            self.send('ImgMode p')
        with self.reset_and_wait_for_event(self, 'Send'):
            self.send('fillpix 0x9d367')
        logger.debug('Read-back-detector finished.')
        if outputfile is not None:
            with self.reset_and_wait_for_event(self, 'Send'):
                self.send('Imgonly ' + outputfile)
            return self.lastresults['Send'][2]['Send']
    def calibrate(self, outputfile=None):
        logger.debug('Calibration started...')
        with self.reset_and_wait_for_event(self, 'Send'):
            self.send('ImgMode p')
        with self.reset_and_wait_for_event(self, 'Send', timeout=60):
            self.send('calibrate')
        logger.debug('Calibration finished.')
        if outputfile is not None:
            with self.reset_and_wait_for_event(self, 'Send'):
                self.send('Imgonly ' + outputfile)
            return self.lastresults['Send'][2]['Send']
    def getthreshold(self):
        with self.reset_and_wait_for_event(self, 'SetThreshold'):
            self.send('SetThreshold')
        return self.lastresults['SetThreshold'][2]
    def wait_for_idle(self, timeout=1):
        while self.camstate != 'idle':
            time.sleep(timeout)
    @GObject.property
    def imgmode(self):
        with self.reset_and_wait_for_event(self, 'ImgMode'):
            self.send('ImgMode')
        return self.lastresults['ImgMode'][2]['imgmode']
    @imgmode.setter
    def imgmode(self, imgmode):
        with self.reset_and_wait_for_event(self, 'Send'):
            self.send('ImgMode ' + imgmode)
    @GObject.property
    def tau(self):
        with self.reset_and_wait_for_event(self, 'Tau'):
            self.send('Tau')
        return self.lastresults['Tau'][2]['tau']
    @tau.setter
    def tau(self, value):
        with self.reset_and_wait_for_event(self, ['Send', 'Tau'], timeout=0.5):
            self.send('Tau %g' % value)

