from .instrument import Instrument_TCP, InstrumentError, InstrumentStatus, Command, CommandReply
import logging
from gi.repository import GObject
from ...utils import objwithgui
import os
import threading
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class VacuumGaugeError(InstrumentError):
    pass

class VacuumGauge(Instrument_TCP):
    logfile = GObject.property(type=str, default='log.vac', blurb='Log file')
    logtimeout = GObject.property(type=float, default=5, minimum=1, blurb='Logging interval (sec)')
    def __init__(self):
        self._OWG_init_lists()
        self._OWG_entrytypes['logfile'] = objwithgui.OWG_Param_Type.File
        Instrument_TCP.__init__(self)
        self.timeout = 0.1
        self.timeout2 = 0.1
        self.port = 2002
        self._logthread = None
        self._logthread_stop = threading.Event()
    def _post_connect(self):
        logger.info('Connected to vacuum gauge: ' + self.get_version())
        self._restart_logger()
    def _pre_disconnect(self, should_do_communication):
        if self._logthread is not None:
            logger.info('Shutting down vacuum logger thread before disconnecting from instrument.')
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
        logger.info('(Re)started vacuum logger thread. Target: ' + self.logfile + ', timeout: %.2f sec' % self.logtimeout)
    def execute(self, code, data=''):
        mesg = '001' + code + data
        mesg = mesg + chr(sum(ord(x) for x in mesg) % 64 + 64) + '\r'
        result = self.send_and_receive(mesg, blocking=True)
        message = self.interpret_message(result, code)
        return message
    def interpret_message(self, message, command=None):
        if command is None:
            logger.warning('Asynchronous commands not supported for vacuum gauge!')
            return None
        if message[-1] != '\r':
            raise VacuumGaugeError('Invalid message: does not end with CR: ' + message)
        if chr(sum(ord(x) for x in message[:-2]) % 64 + 64) != message[-2]:
            raise VacuumGaugeError('Invalid message: checksum error: ' + message)
        if not message.startswith('001' + command):
            raise VacuumGaugeError('Invalid message: should start with 001' + command + ': ' + message)
        return message[4:-2]
    def _parse_float(self, message):
        return float(message[:4]) * 10 ** (float(message[4:6]) - 23)
    def readout(self):
        return self._parse_float(self.execute('M'))
    def get_version(self):
        if not hasattr(self, '_version'):
            self._version = self.execute('T')
        return self._version
    def get_units(self):
        return ['mbar', 'Torr', 'hPa'][int(self.execute('U'))]
    def set_units(self, units='mbar'):
        self.execute('u', '%06d' % ({'mbar':0, 'Torr':1, 'hPa':2}[units]))
    def get_current_parameters(self):
        return {'Vacuum':self.readout(), 'VacuumGauge':self.get_version()}
    def _logger_thread(self, stopswitch, logfile):
        try:
            while True:
                if not self.connected():
                    break
                data = self.readout()
                t = time.time()
                with open(logfile, 'at') as f:
                    f.write('%.3f\t%.3f\n' % (t, data))
                if stopswitch.wait(self.logtimeout):
                    logger.debug('Stopping logger thread')
                    break
        except Exception as vge:
            logger.error('Breaking logger thread because of an error: ' + vge.message)
    def wait_for_vacuum(self, pthreshold=1.0, alternative_breakfunc=lambda :False):
        """Wait until the vacuum becomes better than pthreshold or alternative_breakfunc() returns True. 
        During the wait, this calls the default GObject main loop.
        """
        while not (self.readout() <= pthreshold or alternative_breakfunc()):
            for i in range(100):
                GObject.main_context_default().iteration(False)
                if not GObject.main_context_default().pending():
                    break
        return (not alternative_breakfunc())
