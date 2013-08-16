from .instrument import Instrument_TCP, InstrumentError, InstrumentStatus, Command, CommandReply
import logging
from gi.repository import GObject
from ...utils import objwithgui
import os
import threading
import time
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class HaakePhoenixError(InstrumentError):
    pass

class HaakePhoenix(Instrument_TCP):
    logfile = GObject.property(type=str, default='log.temp', blurb='Log file')
    logtimeout = GObject.property(type=float, default=5, minimum=1, blurb='Logging interval (sec)')
    def __init__(self, offline=True):
        self._OWG_init_lists()
        self._OWG_entrytypes['logfile'] = objwithgui.OWG_Param_Type.File
        Instrument_TCP.__init__(self, offline)
        self.timeout = 0.1
        self.timeout2 = 0.1
        self.port = 2003
        
        self._logthread = None
        self._logthread_stop = threading.Event()
    def _post_connect(self):
        logger.info('Connected to Haake Phoenix circulator: ' + self.get_version())
        self._restart_logger()
    def _pre_disconnect(self, should_do_communication):
        if self._logthread is not None:
            logger.info('Shutting down temperature logger thread before disconnecting from instrument.')
            self._logthread_stop.set()
            self._logthread.join()
            self._logthread_stop.clear()
            self._logthread = None
        if hasattr(self, '_version'):
            del self._version
    def do_notify(self, prop):
        Instrument_TCP.do_notify(self, prop)
        if prop.name == 'logfile':
            if not os.path.isabs(self.logfile):
                self.logfile = os.path.abspath(self.logfile)
            else:
                if self.connected():
                    self._restart_logger()
    def _restart_logger(self):
        if self._logthread is not None:
            self._logthread_stop.set()
            self._logthread.join()
            self._logthread = None
        self._logthread = threading.Thread(target=self._logger_thread, args=(self._logthread_stop, self.logfile))
        self._logthread.daemon = True
        self._logthread_stop.clear()
        self._logthread.start()
        logger.info('(Re)started temperature logger thread. Target: ' + self.logfile + ', timeout: %.2f sec' % self.logtimeout)
    def execute(self, command, postprocessor=lambda x:x, retries=3):
        for i in range(retries):
            try:
                result = self.send_and_receive(command + '\r', blocking=True)
                message = self.interpret_message(result, command)
                return postprocessor(message)
            except InstrumentError as ie:
                if i > 1:
                    logger.warning('Haake Phoenix communication error on command %s (try %d/%d): %s' % (command, i + 1, retries, ie.message))
                if i >= retries - 1:
                    raise HaakePhoenixError('Communication error on command %s. %d retries exhausted. Error: %s' % (command, retries, ie.message))
    def interpret_message(self, message, command=None):
        if command is None:
            logger.warning('Asynchronous commands not supported for vacuum gauge!')
            return None
        if message[-1] != '\r':
            raise HaakePhoenixError('Invalid message: does not end with CR: ' + message)
        return message[:-1]
    def _parse_temperature(self, mesg):
        m = re.match('([+-]\d\d\d\d.\d\d) [CKF]\$', mesg)
        if m is None:
            raise HaakePhoenixError('Invalid temperature data received: %s' % mesg)
        return float(m.group(1))
    def get_temperature(self):
        return self.execute('I', self._parse_temperature)
    def get_setpoint(self):
        return self.execute('S', self._parse_temperature)
    def start_circulation(self):
        self.execute('GO')
    def stop_circulation(self):
        self.execute('ST')
    def is_circulating(self):
        return self.get_pumppower() > 0
    def _parse_pumppower(self, mesg):
        m = re.match('PF(\d+\.\d+)\$', mesg)
        if m is None:
            raise HaakePhoenixError('Invalid pump power data received: %s' % mesg)
        return float(m.group(1))
    def get_pumppower(self):
        return self.execute('r pf', self._parse_pumppower)
    def set_setpoint(self, temp, verify=True):
        if (temp < -50) or (temp > 200):
            raise HaakePhoenixError('Temperature outside limits.')
        cmd = 'S  %05d' % (temp * 100)
        if verify:
            for i in range(3):
                try:
                    self.execute(cmd)
                    setpoint = self.get_setpoint()
                    if abs(setpoint - temp) > 0.01:
                        raise HaakePhoenixError('Could not set setpoint on Haake Phoenix!')
                    else:
                        return True
                except HaakePhoenixError as hpe:
                    logger.warning(hpe.message)
            raise HaakePhoenixError('Could not set setpoint on Haake Phoenix!')
        else:
            return True
                    
                    
                
    def get_version(self):
        if not hasattr(self, '_version'):
            logger.debug('Trying to read version.')
            self._version = self.execute('V')
        return self._version
    def get_current_parameters(self):
        if self.connected():
            return {'Temperature':self.get_temperature(), 'TemperatureController':self.get_version()}
        else:
            return {'Temperature':None, 'TemperatureController':'Disconnected'}
    def _logger_thread(self, stopswitch, logfile):
        try:
            while True:
                if not self.connected():
                    break
                data = self.get_temperature()
                setpoint = self.get_setpoint()
                t = time.time()
                with open(logfile, 'at') as f:
                    f.write('%.3f\t%.3f\t%.3f\n' % (t, data, setpoint))
                if stopswitch.wait(self.logtimeout):
                    logger.debug('Stopping logger thread')
                    break
        except Exception as vge:
            logger.error('Breaking logger thread because of an error: ' + vge.message)
    def wait_for_temperature(self, interval, delta=0.01, setpoint=None, alternative_breakfunc=lambda :False):
        """Wait until the vacuum becomes better than pthreshold or alternative_breakfunc() returns True. 
        During the wait, this calls the default GObject main loop.
        """
        if setpoint is None:
            setpoint = self.get_setpoint()
        lastwrong = time.time()
        while not ((time.time() - lastwrong) > interval or alternative_breakfunc()):
            for i in range(100):
                GObject.main_context_default().iteration(False)
                if not GObject.main_context_default().pending():
                    break
            if abs(setpoint - self.get_temperature()) > delta:
                lastwrong = time.time()
        return (not alternative_breakfunc())
