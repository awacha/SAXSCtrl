from .instrument import Instrument_TCP, InstrumentError, InstrumentProperty, InstrumentPropertyCategory
import logging
from gi.repository import GLib
from ...utils import objwithgui
import time
import traceback
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HaakePhoenixError(InstrumentError):
    pass


class HaakePhoenix(Instrument_TCP):
    __gtype_name__ = 'SAXSCtrl_Instrument_HaakePhoenix'
    setpoint = InstrumentProperty(
        name='setpoint', type=float, timeout=1, refreshinterval=1)
    temperature = InstrumentProperty(
        name='temperature', type=float, timeout=1, refreshinterval=1)
    difftemp = InstrumentProperty(
        name='difftemp', type=float, timeout=1, refreshinterval=1)
    version = InstrumentProperty(
        name='version', type=str, timeout=3600, refreshinterval=3600)
    pumppower = InstrumentProperty(
        name='pumppower', type=float, timeout=1, refreshinterval=1)
    temperaturecontrol = InstrumentProperty(
        name='temperaturecontrol', type=bool, timeout=1, refreshinterval=1)
    externalcontrol = InstrumentProperty(
        name='externalcontrol', type=bool, timeout=1, refreshinterval=1)
    mainrelay_fault = InstrumentProperty(
        name='mainrelay_fault', type=bool, timeout=1, refreshinterval=1)
    overtemperature_fault = InstrumentProperty(
        name='overtemperature_fault', type=bool, timeout=1, refreshinterval=1)
    liquidlevel_fault = InstrumentProperty(
        name='liquidlevel_fault', type=bool, timeout=1, refreshinterval=1)
    motor_overload_fault = InstrumentProperty(
        name='motor_overload_fault', type=bool, timeout=1, refreshinterval=1)
    external_connection_fault = InstrumentProperty(
        name='external_connection_fault', type=bool, timeout=1, refreshinterval=1)
    cooling_fault = InstrumentProperty(
        name='cooling_fault', type=bool, timeout=1, refreshinterval=1)
    internal_pt100_fault = InstrumentProperty(
        name='internal_pt100_fault', type=bool, timeout=1, refreshinterval=1)
    external_pt100_fault = InstrumentProperty(
        name='external_pt100_fault', type=bool, timeout=1, refreshinterval=1)
    iscooling = InstrumentProperty(
        name='iscooling', type=bool, timeout=1, refreshinterval=1)
    _stateflags = ['temperaturecontrol', 'externalcontrol', 'mainrelay_fault', 'overtemperature_fault',
                   'liquidlevel_fault', 'motor_overload_fault', 'external_connection_fault',
                   'cooling_fault', 'internal_pt100_fault', 'external_pt100_fault']

    def _parse_stateflags(self, message):
        m = re.match('(?P<temperaturecontrol>[01])(?P<externalcontrol>[01])(?P<mainrelay_fault>[01])(?P<overtemperature_fault>[01])'
                     '(?P<liquidlevel_fault>[01])(?P<motor_overload_fault>[01])(?P<external_connection_fault>[01])'
                     '(?P<cooling_fault>[01])(?P<reserved1>[01])(?P<reserved2>[01])(?P<internal_pt100_fault>[01])'
                     '(?P<external_pt100_fault>[01])\$', message)
        if m is None:
            raise HaakePhoenixError(
                'Invalid state flags data received: %s' % message)
        gd = m.groupdict()
        for k in gd:
            gd[k] = (gd[k] == '1')

        return {k: gd[k] for k in gd if not k.startswith('reserved')}

    def __init__(self, name='circulator', offline=True):
        self._OWG_init_lists()
        self._OWG_entrytypes['logfile'] = objwithgui.OWG_Param_Type.File
        Instrument_TCP.__init__(self, name, offline)
        self.timeout = 0.1
        self.timeout2 = 0.1
        self.port = 2003
        self.logfile = 'log.temp'
        self._logging_parameters = [
            ('temperature', 'f4', '%.3f'), ('setpoint', 'f4', '%.3f'), ('pumppower', 'i', '%d')]

    def _update_instrumentproperties(self, propertyname=None):
        if (propertyname is not None) and (propertyname in self._instrumentproperties):
            oldtuple = self._instrumentproperties[propertyname]
            self._instrumentproperties[propertyname] = (
                oldtuple[0], 0, oldtuple[2])
        if self.is_instrumentproperty_expired('setpoint'):
            try:
                type(self).setpoint._update(
                    self, self.get_setpoint(), InstrumentPropertyCategory.NORMAL)
            except HaakePhoenixError:
                logger.warn(
                    'InstrumentError while getting setpoint from Haake Phoenix circulator: ' + traceback.format_exc())
                type(self).setpoint._update(
                    self, None, InstrumentPropertyCategory.UNKNOWN)
        if self.is_instrumentproperty_expired('pumppower'):
            try:
                pumppower = self.get_pumppower()
                type(self).pumppower._update(self, pumppower, [
                    InstrumentPropertyCategory.NO, InstrumentPropertyCategory.YES][int(pumppower != 0) % 2])
            except HaakePhoenixError:
                logger.warn(
                    'InstrumentError while getting pump power from Haake Phoenix circulator: ' + traceback.format_exc())
                type(self).pumppower._update(
                    self, None, InstrumentPropertyCategory.UNKNOWN)
        if self.is_instrumentproperty_expired('version'):
            try:
                type(self).version._update(
                    self, self.get_version(), InstrumentPropertyCategory.NORMAL)
            except HaakePhoenixError:
                logger.warn(
                    'InstrumentError while getting version string from Haake Phoenix circulator: ' + traceback.format_exc())
                type(self).version._update(
                    self, None, InstrumentPropertyCategory.UNKNOWN)
        if self.is_instrumentproperty_expired('temperature'):
            try:
                temp = self.get_temperature()
                type(self).temperature._update(
                    self, temp, InstrumentPropertyCategory.NORMAL)
            except HaakePhoenixError:
                logger.warn(
                    'InstrumentError while getting temperature from Haake Phoenix circulator: ' + traceback.format_exc())
                type(self).temperature._update(
                    self, None, InstrumentPropertyCategory.UNKNOWN)
        if self.is_instrumentproperty_expired('difftemp'):
            try:
                type(self).difftemp._update(
                    self, self.temperature - self.setpoint, InstrumentPropertyCategory.NORMAL)
            except (HaakePhoenixError, TypeError):
                logger.warn(
                    'InstrumentError while getting temperature delta from Haake Phoenix circulator: ' + traceback.format_exc())
                type(self).difftemp._update(
                    self, None, InstrumentPropertyCategory.UNKNOWN)
        if self.is_instrumentproperty_expired('iscooling'):
            try:
                value = self.get_cooling_state()
                type(self).iscooling._update(self, value, [
                    InstrumentPropertyCategory.NO, InstrumentPropertyCategory.YES][int(value) % 2])
            except HaakePhoenixError:
                logger.warn(
                    'InstrumentError while getting cooling state from Haake Phoenix circulator: ' + traceback.format_exc())
                type(self).iscooling._update(
                    self, None, InstrumentPropertyCategory.UNKNOWN)
        try:
            stateflags = self.get_stateflags()
        except HaakePhoenixError:
            logger.warn(
                'InstrumentError while getting state flags from Haake Phoenix circulator: ' + traceback.format_exc())
            for flag in self._stateflags:
                getattr(type(self), flag)._update(
                    self, None, InstrumentPropertyCategory.UNKNOWN)
        else:
            for flag in stateflags:
                if flag.endswith('fault'):
                    if stateflags[flag]:
                        category = InstrumentPropertyCategory.ERROR
                    else:
                        category = InstrumentPropertyCategory.OK
                elif flag == 'temperaturecontrol':
                    category = [InstrumentPropertyCategory.NO, InstrumentPropertyCategory.YES][
                        int(stateflags[flag]) % 2]
                elif flag == 'externalcontrol':
                    category = InstrumentPropertyCategory.NORMAL
                else:
                    raise NotImplementedError(
                        'Unknown Haake Phoenix status flag: ' + flag)
                getattr(type(self), flag)._update(
                    self, stateflags[flag], category)

    def _post_connect(self):
        logger.info(
            'Connected to Haake Phoenix circulator: ' + self.get_version())

    def _pre_disconnect(self, should_do_communication):
        if hasattr(self, '_version'):
            del self._version

    def execute(self, command, postprocessor=lambda x: x, retries=3):
        for i in range(retries):
            try:
                result = self.send_and_receive(command + '\r', blocking=True)
                message = self.interpret_message(result, command)
                return postprocessor(message)
            except InstrumentError as ie:
                if i > 1:
                    logger.warning('Haake Phoenix communication error on command %s (try %d/%d): %s' % (
                        command, i + 1, retries, traceback.format_exc()))
                if i >= retries - 1:
                    raise HaakePhoenixError('Communication error on command %s. %d retries exhausted. Error: %s' % (
                        command, retries, traceback.format_exc()))

    def interpret_message(self, message, command=None):
        if command is None:
            logger.warning(
                'Asynchronous commands not supported for Haake Phoenix!')
            return None
        if message[-1] != '\r':
            raise HaakePhoenixError(
                'Invalid message: does not end with CR: ' + message)
        return message[:-1]

    def _parse_temperature(self, mesg):
        m = re.match('([+-]\d\d\d\d.\d\d) [CKF]\$', mesg)
        if m is None:
            raise HaakePhoenixError(
                'Invalid temperature data received: %s' % mesg)
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
            raise HaakePhoenixError(
                'Invalid pump power data received: %s' % mesg)
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
                        raise HaakePhoenixError(
                            'Could not set setpoint on Haake Phoenix!')
                    else:
                        return True
                except HaakePhoenixError as hpe:
                    logger.warning(
                        'Error setting setpoint in Haake Phoenix circulator: ' + traceback.format_exc())
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
            dic = {}
            for name, parname in [('Temperature', 'temperature'),
                                  ('TemperatureController', 'version'),
                                  ('TemperatureSetpoint', 'setpoint'),
                                  ('PumpPower', 'pumppower')]:
                dic[name] = self.get_instrument_property(parname)[0]
            return dic
        else:
            return {'Temperature': None, 'TemperatureController': 'Disconnected', 'TemperatureSetpoint': None, 'PumpPower': None}

    def wait_for_temperature(self, interval, delta=0.01, setpoint=None, alternative_breakfunc=lambda: False):
        """Wait until the vacuum becomes better than pthreshold or alternative_breakfunc() returns True. 
        During the wait, this calls the default GObject main loop.
        """
        if setpoint is None:
            setpoint = self.get_setpoint()
        lastwrong = time.time()
        while not ((time.time() - lastwrong) > interval or alternative_breakfunc()):
            for i in range(100):
                GLib.main_context_default().iteration(False)
                if not GLib.main_context_default().pending():
                    break
            if abs(setpoint - self.get_temperature()) > delta:
                lastwrong = time.time()
        return (not alternative_breakfunc())

    def get_stateflags(self):
        return self.execute('B', self._parse_stateflags)

    def _parse_coolingstate(self, message):
        m = re.match('CC(?P<coolingstate>[01])\$', message)
        if m is None:
            raise HaakePhoenixError('Invalid cooling state: ' + message)
        return m.group(1) == '1'

    def get_cooling_state(self):
        return self.execute('R CC', self._parse_coolingstate)

    def _get_logline(self):
        try:
            return self._logformatstring() % ((time.time(),) + tuple(getattr(self, x[0]) for x in self._logging_parameters))
        except Exception as ex:
            logger.warn(
                'Exception while logging the state of Haake Phoenix circulator: ' + traceback.format_exc())
            return "# log error: " + str(type(ex)) + " " + str(ex)
