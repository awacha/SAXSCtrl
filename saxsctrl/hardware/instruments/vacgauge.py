from .instrument import Instrument_TCP, InstrumentError, InstrumentStatus, Command, CommandReply
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class VacuumGaugeError(InstrumentError):
    pass

class VacuumGauge(Instrument_TCP):
    def __init__(self):
        Instrument_TCP.__init__(self)
        self.timeout = 0.1
        self.timeout2 = 0.1
        self.port = 2002
    def execute(self, code, data=''):
        mesg = '001' + code + data
        mesg = mesg + chr(sum(ord(x) for x in mesg) % 64 + 64) + '\r'
        result = self.send_and_receive(mesg, blocking=True)
        message = self.interpret_message(result, code)
        return message
    def interpret_message(self, message, command=None):
        if command is None:
            raise VacuumGaugeError('Asynchronous commands not supported!')
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
        return self.execute('T')
    def get_units(self):
        return ['mbar', 'Torr', 'hPa'][int(self.execute('U'))]
    def set_units(self, units='mbar'):
        self.execute('u', '%06d' % ({'mbar':0, 'Torr':1, 'hPa':2}[units]))
    def get_current_parameters(self):
        return {'Vacuum':self.readout(), 'VacuumGauge':self.get_version()}
