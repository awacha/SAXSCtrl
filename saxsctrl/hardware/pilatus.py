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

logger = logging.getLogger(__name__)

class PilatusError(StandardError):
    pass

class CommunicationError(PilatusError):
    pass

class TimeoutError(PilatusError):
    pass

class PilatusConnection(object):
    _in_exposure = False
    _expstarted = None
    _mesglen = 200
    _status = {}
    _status_timeout = 0.1
    _status_time = None
    _pilatus_lock = None
    _timeout_handler = None
    _recvthread = None
    _recvthread_iotimeout = 1  # time-out for select.select() in the receiving thread in seconds.
    _kill_recvthread = None  # event signifying to the receiving thread to stop.
    _eventnames = ['setackint', 'expperiod', 'nimages', 'disconnect_from_camserver', 'imgmode', 'setthreshold', 'mxsettings', 'camsetup', 'exptime', 'OK', 'exposure', 'expend', 'exposure_finished', 'imgpath', 'df', 'thread']
    def __init__(self, host='localhost', port=41234):
        self._pilatus_lock = threading.Lock()
        self._sendqueue = Queue.Queue()
        self.socket = None
        self.events = {}
        for e in self._eventnames:
            self.events[e] = [threading.Event(), None, None, {}]  # event itself, message, status number, list of connections 
        if host is not None:
            self.connect(host, port)
    def connected(self):
        """Return if connected to camserver"""
        with self._pilatus_lock:
            return self.socket is not None
    def connect(self, host, port=41234):
        """Connect to camserver at host:port.
        """
        with self._pilatus_lock:
            if self.socket is not None:
                raise PilatusError('Cannot connect: connection already open.')
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                ip = socket.gethostbyname(host)
                self.socket.connect((ip, port))
                self._recvthread = threading.Thread(name='Pilatus_receive', target=self._recvthread_worker)
                self._recvthread.setDaemon(True)
                self._kill_recvthread = threading.Event()
                self._recvthread.start()
            except socket.gaierror:
                self.socket = None
                raise PilatusError('Cannot resolve host name.')
            except socket.error:
                self.socket = None
                raise PilatusError('Cannot connect to camserver.')
        logger.info('Connected to server %s:%d' % (host, port))
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
        elif contextnumber == 15 and message.startswith('Exposure time set to:'):
            try:
                self.events['exptime'][1] = float(re.search('\d+\.\d+', message).group(0))
            except (ValueError, AttributeError):
                self.events['exptime'][1] = -1
            self._call_handlers('exptime')
            self.events['exptime'][0].set()
        elif contextnumber == 15 and message.startswith('Command:'):
            # using the demo P6M detector some commands are not implemented.
            cmd = message[8:].strip().split(None, 1)[0]
            if cmd.lower() in self.events:
                self.events[cmd.lower()][0].set()
            elif cmd.lower() in ['fillpix', 'calibrate']:
                self.events['OK'][0].set()
        elif contextnumber == 6:
            self._in_exposure = False
            self.events['expend'][1] = message
            self._call_handlers('expend')
            self.events['expend'][0].set()
        elif contextnumber == 15 and re.search('Starting \d+\.\d+ second', message) is not None:
            m = re.search('Starting (?P<exptime>\d+\.\d+) second (?P<exptype>\w*?): (?P<expdatetime>\d{4,4}-\d{2,2}-\d{2,2}T\d{2,2}:\d{2,2}:\d{2,2}.\d+)', message)
            if m is not None:
                self.events['exposure'][1] = m.groupdict()
                self.events['exposure'][1]['exptime'] = float(self.events['exposure'][1]['exptime'])
                self.events['exposure'][1]['expdatetime'] = dateutil.parser.parse(self.events['exposure'][1]['expdatetime'])
            self._in_exposure = True
            self._expstarted = time.time()
            self._call_handlers('exposure')
            self.events['exposure_finished'][0].clear()
            self.events['exposure'][0].set()
        elif contextnumber == 7:
            self._in_exposure = False
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
            print "Unknown but valid message: ", contextnumber, status, message
        
    def _recvthread_worker(self):
        """worker function for the receiving thread. This is responsible for all the communication over TCP/IP between
        camserver and this class."""
        
        # this function constitutes of a main loop, which can be ended via a ''poison-pill'' mechanism.
        while not self._kill_recvthread.is_set():
            # first check the status of the communications socket.
            with self._pilatus_lock:
                readable, writable, exceptional = select.select([self.socket], [self.socket], [self.socket], self._recvthread_iotimeout)
                # first try to send, if the socket is writable
                while writable:
                    # check if the queue contains messages to be sent.
                    try:
                        msgtosend = self._sendqueue.get_nowait()
                    except Queue.Empty:
                        # if no messages, break the loop.
                        break
                    # separate the command part and check if we have a corresponding event.
                    cmd = msgtosend.strip().split()[0]
                    if cmd.lower() in self.events:
                        # if we do, clear its flag, so corresponding wait_for_event() calls will not escape before the event is raised.
                        self.events[cmd][0].clear()
                    try:
                        # pad the message to the given length.
                        mesg1 = msgtosend + ' ' * (self._mesglen - len(msgtosend))
                        chars_sent = 0
                        while chars_sent < self._mesglen:
                            chars_sent += self.socket.send(mesg1[chars_sent:])
                        logging.debug('PILATUS_SEND: ' + msgtosend)
                    except socket.error:
                        self.socket.close()
                        self.socket = None
                        # kill ourselves.
                        self.events['disconnect_from_camserver'][1] = 'error'
                        self._call_handlers('disconnect_from_camserver')
                        return
                    
                    writable = select.select([self.socket], [], [], 0)[1]

                readable, writable, exceptional = select.select([self.socket], [self.socket], [self.socket], self._recvthread_iotimeout)
                mesg = ''
                while readable:
                    newmesg = self.socket.recv(self._mesglen)
                    if not newmesg:  # was readable but 0 bytes received: socket closed.
                        self.socket.close()
                        self.socket = None
                        # kill ourselves.
                        self.events['disconnect_from_camserver'][1] = 'error'
                        self._call_handlers('disconnect_from_camserver')
                        return
                    mesg = mesg + newmesg
                    readable = select.select([self.socket], [], [], 0)[0]
                    logging.debug('PILATUS_READ: ' + newmesg)

            # for the next operations, we do not need the communications lock.        
            
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
                self._interpret_message(contextnumber, state, message)
        return
    def _call_handlers(self, eventname):
        for uuid in self.events[eventname][3]:
            self.events[eventname][3][uuid](self.events[eventname][1], self.events[eventname][2])
    def send(self, mesg):
        if not self.connected():
            raise CommunicationError('Socket closed')
        logger.debug('sending message: ' + mesg)
        self._sendqueue.put(mesg)
    def disconnect(self):
        if self.socket is None: return
        self._kill_recvthread.set()
        self._recvthread.join()
        with self._pilatus_lock:
            self.socket.close()
            self.socket = None
        self.events['disconnect_from_camserver'][1] = 'normal'
        self._call_handlers('disconnect_from_camserver')
    def __del__(self):
        self.disconnect()
    def get_status(self, force=False):
        if self._status_time is not None and (time.time() - self._status_time) < self._status_timeout and not force:
            return self._status
        elif self._in_exposure:
            self._status['timeleft'] = self._status['exptime'] - (time.time() - self._expstarted)
            self._status['state'] = 'exposing'
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
            logger.info('Starting %f seconds exposure to filename %s.' % (exptime, filename))
        else:
            logger.info('Starting %d exposures. Exptime: %f seconds. Period: %f seconds. Starting file: %s' % (Nimages, exptime, exptime + expdwelltime, filename))
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
        logger.info('Stopping running exposure.')
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
        logger.info('Setting threshold to %d eV (gain: %s)' % (threshold, gain))
        self.send('setthreshold %s %d' % (gain, threshold))
        data = self.wait_for_event('setthreshold', 60)[0]
        return data
    def rbd(self):
        logger.info('Read-back-detector starting...')
        self.send('imgmode p')
        self.wait_for_event('OK')
        self.send('fillpix 0x9d367')
        self.wait_for_event('OK')
        self.wait_for_idle()
        logger.info('Read-back-detector finished.')
    def calibrate(self):
        logger.info('Calibration started...')
        self.send('imgmode p')
        self.wait_for_event('OK')
        self.send('calibrate')
        self.wait_for_event('OK')
        self.wait_for_idle()
        logger.info('Calibration finished.')
    def wait_for_idle(self, timeout=1):
        while self.camstate != 'idle':
            time.sleep(timeout)
        
        
