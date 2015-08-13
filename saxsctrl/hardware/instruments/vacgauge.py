from .instrument import Instrument_TCP, InstrumentError, ConnectionBrokenError, InstrumentProperty, InstrumentPropertyCategory
import logging
from gi.repository import GObject
from gi.repository import GLib
from ...utils import objwithgui
import traceback
import binascii

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class VacuumGaugeError(InstrumentError):
    pass


class VacuumGauge(Instrument_TCP):
    send_recv_retries = GObject.property(
        type=int, minimum=1, default=3, blurb='Number of retries on communication failure')
    pressure = InstrumentProperty(
        name='pressure', type=float, refreshinterval=1, timeout=1)

    def __init__(self, name='vacuumgauge', offline=True):
        self._OWG_init_lists()
        self._OWG_entrytypes['logfile'] = objwithgui.OWG_Param_Type.File
        Instrument_TCP.__init__(self, name, offline)
        self.timeout = 0.1
        self.timeout2 = 0.1
        self.port = 2002
        self.logfile = 'log.vac'
        self._logging_parameters = [('pressure', 'f4', '%.3f')]

    def __idle__(self, status):
        m = re.match('(?P<value>\d+(\.\d*)?) mbar', status)
        if m is None:
            raise NotImplementedError
        return m.group_dict()['value'] < 0.01

    def _update_instrumentproperties(self, propertyname=None):
        try:
            pressure = self.readout()
            if pressure < 0.1:
                categ = InstrumentPropertyCategory.NORMAL
            elif pressure < 1:
                categ = InstrumentPropertyCategory.WARNING
            else:
                categ = InstrumentPropertyCategory.ERROR
            statformatted = '%.3f mbar' % pressure
            if self.status != statformatted:
                self.status = statformatted
        except (InstrumentError, ValueError):
            pressure = 0
            categ = InstrumentPropertyCategory.UNKNOWN
        type(self).pressure._update(self, pressure, categ)

    def _post_connect(self):
        logger.info(
            'Connected to vacuum gauge: ' + self.get_version().decode('ascii'))

    def _pre_disconnect(self, should_do_communication):
        if hasattr(self, '_version'):
            del self._version

    def execute(self, code, data=b''):
        mesg = b'001' + code + data
        mesg = mesg + bytes((sum(mesg) % 64 + 64,)) + b'\r'
        for i in range(self.send_recv_retries - 1, -1, -1):
            try:
                result = self.send_and_receive(mesg, blocking=True)
                message = self.interpret_message(result, code)
                break
            except VacuumGaugeError as vge:
                if not i:
                    raise
                logger.warning(
                    'Communication error; retrying (%d retries left): ' % i + traceback.format_exc())
            except (ConnectionBrokenError, InstrumentError) as exc:
                logger.error('Connection of instrument %s broken: ' %
                             self._get_classname() + traceback.format_exc())
                raise VacuumGaugeError(
                    'Connection broken: ' + traceback.format_exc())
            except Exception as exc:
                logger.error('Instrument error on module %s: ' %
                             self._get_classname() + traceback.format_exc())
                raise VacuumGaugeError(
                    'Instrument error: ' + traceback.format_exc())

        return message

    def interpret_message(self, message, command=None):
        if command is None:
            logger.warning(
                'Asynchronous commands not supported for vacuum gauge!')
            return None
        if message[-1] != b'\r'[0]:
            raise VacuumGaugeError(
                'Invalid message: does not end with CR: 0x' + str(binascii.hexlify(message)))
        if sum(message[:-2]) % 64 + 64 != message[-2]:
            raise VacuumGaugeError(
                'Invalid message: checksum error: 0x' + str(binascii.hexlify(message)))
        if not message.startswith(b'001' + command):
            raise VacuumGaugeError('Invalid message: should start with ' +
                                   str(b'001' + command) + ': 0x' + str(binascii.hexlify(message)))
        return message[4:-2]

    def _parse_float(self, message):
        return float(message[:4]) * 10 ** (float(message[4:6]) - 23)

    def readout(self):
        return self._parse_float(self.execute(b'M'))

    def get_version(self):
        if not hasattr(self, '_version'):
            self._version = self.execute(b'T')
        return self._version

    def get_units(self):
        return ['mbar', 'Torr', 'hPa'][int(self.execute(b'U'))]

    def set_units(self, units='mbar'):
        self.execute(b'u', b'%06d' % ({'mbar': 0, 'Torr': 1, 'hPa': 2}[units]))

    def get_current_parameters(self):
        return {'Vacuum': self.get_instrument_property('pressure')[0], 'VacuumGauge': self.get_version()}

    def wait_for_vacuum(self, pthreshold=1.0, alternative_breakfunc=lambda: False):
        """Wait until the vacuum becomes better than pthreshold or alternative_breakfunc() returns True.
        During the wait, this calls the default GObject main loop.
        """
        while not (self.pressure <= pthreshold or alternative_breakfunc()):
            for i in range(100):
                GLib.main_context_default().iteration(False)
                if not GLib.main_context_default().pending():
                    break
        return (not alternative_breakfunc())
