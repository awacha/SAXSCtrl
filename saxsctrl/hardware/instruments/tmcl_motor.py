import logging
import struct
import multiprocessing.queues
import weakref
import ConfigParser
import numbers
from gi.repository import GObject
from gi.repository import GLib
import nxs

from .instrument import Instrument_TCP, InstrumentError, InstrumentStatus, ConnectionBrokenError
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class MotorError(InstrumentError):
    pass

class TMCMModuleStatus(InstrumentStatus):
    Moving = 'moving'
    Queued = 'queued'

class StepperStatus(InstrumentStatus):
    Queued = 'queued'
    Moving = 'moving'
    pass

class TMCMModule(Instrument_TCP):
    __gsignals__ = {'motors-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'motor-start':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'motor-report':(GObject.SignalFlags.RUN_FIRST, None, (object, float, float, float)),
                    'motor-stop':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'motor-limit':(GObject.SignalFlags.RUN_FIRST, None, (object, bool, bool)),
                    'motor-settings-changed':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    }
    _considered_idle = [TMCMModuleStatus.Disconnected, TMCMModuleStatus.Idle]
    send_recv_retries = GObject.property(type=int, minimum=1, default=3, blurb='Number of retries on communication failure')
    savesettings_delay = GObject.property(type=float, minimum=0, default=0.5, blurb='Delay for saving settings')
    _motor_counter = 1
    _max_motors_in_motion = 1
    def __init__(self, name='motordriver', offline=True):
        self.motors = {}
        self.f_clk = 16000000
        self._adjust_hwtype()
        Instrument_TCP.__init__(self, name, offline)
        self.timeout = 0.1
        self.timeout2 = 0.1
        self.recvbufsize = 8
        self.port = 2001
        self.cmdqueue = multiprocessing.queues.Queue()
        self._motorsemaphore = multiprocessing.Semaphore(self._max_motors_in_motion)

    def _adjust_hwtype(self):
        raise NotImplementedError('Cannot instantiate TMCMModule directly!')

    def _post_connect(self):
        try:
            major, minor, hwtype = self.get_version()
            if hwtype != self.hwtype:
                raise MotorError('Invalid controller type connected. Expected: %s. Got: %s.' % (self.hwtype, hwtype))
            logger.info('Connected stepper controller&driver module: %s (firmware version: %d.%d)' % (hwtype, major, minor))
        except InstrumentError:
            # self.disconnect_from_controller(False)
            raise
        logger.debug('TCP and RS232 both OK.')
        self.load_settings()

    def motorstop(self, flushqueues=True):
        if flushqueues:
            for m in self:
                m.flush_queue()
        for m in self.moving():
            m.stop()

    def __del__(self):
        for m in self.motors.keys():
            del self.motors[m]

    def save_settings_delayed(self):
        if hasattr(self, '_savesettings_delayed_handle'):
            return False
        self._savesettings_delayed_handle = GLib.timeout_add(int(self.savesettings_delay * 1000), lambda : (self.save_settings() and False))

    def save_settings(self, filename=None):
        if hasattr(self, '_savesettings_delayed_handle'):
            del self._savesettings_delayed_handle
        if hasattr(self, '_settingsfile_in_use'):
            return
        if self.offline:
            logger.warning('Not saving motor state: we are off-line')
            return
        self._settingsfile_in_use = True
        try:
            if filename is None:
                filename = self.configfile
            if filename is None:
                return
            cp = ConfigParser.ConfigParser()
            cp.read(filename)
            for m in self.motors:
                self.motors[m].save_to_configparser(cp)
            with open(filename, 'w') as f:
                cp.write(f)
            logger.debug("Saved %s settings to " % self.hwtype + filename)
            return True
        finally:
            del self._settingsfile_in_use

    def load_settings(self, filename=None):
        if hasattr(self, '_settingsfile_in_use'):
            return
        self._settingsfile_in_use = True
        try:
            if filename is None:
                filename = self.configfile
            if filename is None:
                return
            cp = ConfigParser.ConfigParser()
            cp.read(filename)
            for name in cp.sections():
                if name not in self.motors:
                    self.add_motor(0, name)
                self.motors[name].load_from_configparser(cp)
            self.settingsfile = filename
        finally:
            del self._settingsfile_in_use

    def do_communication(self, cmd):
        raise NotImplementedError

    def interpret_message(self, message, command=None):
        if command is None:
            logger.warning('Asynchronous messages not supported for TMCM modules! (got message of length ' + str(len(message)))
            return None
        if len(message) != 9:
            raise MotorError('Number of characters in message is not 9, but ' + str(len(message)))
        if (command != 136) and (not (sum(ord(x) for x in message[:-1]) % 256 == ord(message[-1]))):
            raise MotorError('Checksum error on received data!')
        if not ord(message[3]) == command:
            raise MotorError('Invalid reply from TMCM module: not the same command.')
        status = ord(message[2])
        if status == 1:
            raise MotorError('Wrong checksum of sent message. TMCM response: ' + ''.join('%x' % ord(m) for m in message))
        elif status == 2:
            raise MotorError('Invalid command. TMCM response: ' + ''.join('%x' % ord(m) for m in message))
        elif status == 3:
            raise MotorError('Wrong type. TMCM response: ' + ''.join('%x' % ord(m) for m in message))
        elif status == 4:
            raise MotorError('Invalid value. TMCM response: ' + ''.join('%x' % ord(m) for m in message))
        elif status == 5:
            raise MotorError('Configuration EEPROM locked')
        elif status == 6:
            raise MotorError('Command not available. TMCM response: ' + ''.join('%x' % ord(m) for m in message))
        value = struct.unpack('>i', message[4:8])[0]
        if status != 100:
            raise MotorError('Status not OK! TMCM response: ' + ''.join('%x' % ord(m) for m in message))
        return value

    def execute(self, instruction, type_=0, mot_bank=0, value=0):
        if instruction is not None:
            cmd = (1, instruction, type_, mot_bank) + struct.unpack('4B', struct.pack('>i', int(value)))
            cmd = cmd + (sum(cmd) % 256,)
            logger.debug('About to send TMCL command: ' + ''.join(('%02x' % x) for x in cmd))
            cmd = ''.join(chr(x) for x in cmd)
        else:
            cmd = None
        logger.debug('Sending message to TMCM module: 0x' + ''.join('%x' % ord(x) for x in cmd))
        for i in reversed(range(self.send_recv_retries)):  # self.send_recv_retries-1 to 0.
            try:
                result = self.send_and_receive(cmd, True)
                value = self.interpret_message(result, instruction)
                break
            except MotorError as exc:
                if not i:  # all retries exhausted
                    raise exc
                logger.warning('Communication error: ' + str(exc) + '(type: ' + str(type(exc)) + '); retrying (%d retries left)' % i)
            except (ConnectionBrokenError, InstrumentError) as exc:
                logger.error('Connection of instrument %s broken: ' % self._get_classname() + str(exc))
                raise MotorError('Connection broken: ' + str(exc))
            except Exception as exc:
                logger.error('Instrument error on module %s: ' % self.hwtype + str(exc))
                raise MotorError('Instrument error: ' + str(exc))

        # logger.debug('Got message from TMCM module: 0x' + ''.join('%x' % ord(x) for x in result) + '; interpreted value: ' + str(value))
        # logger.debug('Got TMCL result: ' + ''.join(('%02x' % ord(x)) for x in result))
        # validate checksum, but only if the command is not the get version command.
        return value

    def get_version(self):
        ver = self.execute(136, 1)
        if ver / 0x10000 == 0x015f:
            hwtype = 'TMCM351'
        elif ver / 0x10000 == 0x17de:
            hwtype = 'TMCM6110'
        else:
            raise MotorError('Invalid version signature: ' + hex(ver / 0x10000))
        ver = ver % 0x10000
        major = ver / 0x100
        minor = ver % 0x100
        return major, minor, hwtype

    def add_motor(self, mot_idx, name=None, alias=None, step_to_cal=1 / 200.0, softlimits=(-float('inf'), float('inf'))):
        if (mot_idx < 0) or (mot_idx >= self.n_axes):
            raise MotorError('Cannot add motor with index %d: only %d axes are supported by the controller module.' % (mot_idx, self.n_axes))

        mot = StepperMotor(self, mot_idx, name, alias, step_to_cal, softlimits, self.f_clk)
        mot.connect('motor-start', lambda m:self.emit('motor-start', m))
        mot.connect('motor-report', lambda m, pos, speed, load: self.emit('motor-report', m, pos, speed, load))
        mot.connect('motor-stop', lambda m:self.emit('motor-stop', m))
        mot.connect('motor-limit', lambda m, left, right:self.emit('motor-limit', m, left, right))
        mot.connect('settings-changed', lambda m:self.emit('motor-settings-changed', m))
        if mot.name not in self.motors:
            self.motors[mot.name] = mot
        self.emit('motors-changed')
        return mot

    def moving(self):
        """Return currently moving motors"""
        return [m for m in self if m.is_moving()]

    def get_motor(self, idx):
        if isinstance(idx, numbers.Number):
            return [m for m in self if m.mot_idx == idx][0]
        elif isinstance(idx, basestring):
            return [m for m in self if (m.name == idx) or (m.alias == idx) or (str(m) == idx) ][0]
        else:
            raise NotImplementedError('Invalid type for parameter idx: ', type(idx))

    def do_motor_start(self, mot):
        self.status = TMCMModuleStatus.Moving

    def do_motor_stop(self, mot):
        # a motor movement is finished. Check if the motor has more motion commands
        # in queue. If yes, execute the next of them and return. If not, check
        # other motors if there are queued commands, and execute the first command
        # of the first such motor. If no queued commands are found, become Idle and
        # return.
        if not mot._start_move():
            # no other motions are queued for this motor
            try:
                mot = [m for m in self if m.status == StepperStatus.Queued][0]
                mot._start_move()
                return
            except IndexError:
                # no motions are queued
                self.status = TMCMModuleStatus.Idle
                pass
        else:
            # a motion is started already by mot._start_move().
            pass

    def get_current_parameters(self):
        dic = {}
        for m in self:
            dic[m.alias] = m.get_parameter('Current_position', raw=False)
        return dic

    def do_notify(self, prop):
        Instrument_TCP.do_notify(self, prop)
        if prop.name == 'configfile':
            try:
                self.load_settings(self.configfile)
            except Exception as exc:
                logger.error('Error while calling TMCMModule.load_settings() from do_notify: ' + str(exc))

    def __iter__(self):
        return self.motors.itervalues()

class MotorParameter(object):
    name = ''
    axisparameter_idx = 0
    _tophys = None
    _toraw = None
    _validateraw = None
    _validatephys = None
    readonly = False
    depends = None
    raw_is_phys = False
    datatype = None
    rawminimum = None
    rawmaximum = None
    isinteger = False
    storable = False
    def __init__(self, name, axisparameter_idx, **kwargs):
        self.name = name
        self.axisparameter_idx = axisparameter_idx
        for k in kwargs:
            setattr(self, k, kwargs[k])
        if self.depends is None:
            self.depends = []
    def to_raw(self, value, allparameters):
        if self._toraw is None:
            return value
        else:
            return self._toraw(value, allparameters)
        return
    def to_phys(self, value, allparameters):
        if self._tophys is None:
            return value
        else:
            return self._tophys(value, allparameters)
    def validate(self, value, allparameters):
        valid = True
        if callable(self._validateraw):
            valid &= self._validateraw(self.to_raw(value, allparameters), allparameters)
        if callable(self._validatephys):
            valid &= self._validatephys(value, allparameters)
        return valid

conv_speed_to_raw = lambda x, ap:int(x * 2 ** ap['Pulse_div'] * 2 ** ap['Ustep_resol'] * 2048 * 32 / ap['f_clk'] / ap['step_to_cal'])
conv_speed_to_phys = lambda x, ap: ap['f_clk'] * x / (2 ** ap['Pulse_div'] * 2 ** ap['Ustep_resol'] * 2048 * 32.0) * ap['step_to_cal']

conv_accel_to_raw = lambda x, ap: int(x * 2 ** (ap['Pulse_div'] + ap['Ramp_div'] + 29 + ap['Ustep_resol']) / (ap['step_to_cal'] * ap['f_clk'] ** 2))
conv_accel_to_phys = lambda x, ap: x * ap['f_clk'] ** 2 * ap['step_to_cal'] / 2 ** (ap['Pulse_div'] + ap['Ramp_div'] + 29 + ap['Ustep_resol'])

conv_current_to_raw = lambda x, ap: int(x * 255. / ap['top_rms_current'])
conv_current_to_phys = lambda x, ap: x * ap['top_rms_current'] / 255.

conv_pos_to_phys = lambda x, ap: x * ap['step_to_cal'] / 2 ** ap['Ustep_resol']
conv_pos_to_raw = lambda x, ap: int(x * 2 ** ap['Ustep_resol'] / ap['step_to_cal'])


COMMON_MOTOR_PARAMETERS = [
                           MotorParameter('Pulse_div', 154, _validatephys=lambda x, ap:(0 <= x) & (x <= 13), raw_is_phys=True,
                                          rawminimum=0, rawmaximum=13, isinteger=True, storable=True),
                           MotorParameter('Ramp_div', 153, _validatephys=lambda x, ap:(0 <= x) & (x <= 13), raw_is_phys=True,
                                          rawminimum=0, rawmaximum=13, isinteger=True, storable=True),
                           MotorParameter('Max_speed', 4, _validateraw=lambda x, ap:(0 <= x) & (x <= 2047),
                                          _tophys=conv_speed_to_phys,
                                          _toraw=conv_speed_to_raw,
                                          depends=['f_clk', 'Pulse_div', 'Ustep_resol', 'step_to_cal'],
                                          rawminimum=0, rawmaximum=2047, isinteger=False, storable=True,
                                          ),
                             MotorParameter('Max_accel', 5, _validateraw=lambda x, ap: (0 <= x) & (x <= 2047),
                                            _tophys=conv_accel_to_phys,
                                            _toraw=conv_accel_to_raw,
                                            depends=['f_clk', 'Pulse_div', 'Ustep_resol', 'step_to_cal', 'Ramp_div'],
                                           rawminimum=0, rawmaximum=2047, isinteger=False, storable=True,
                                            ),
                             MotorParameter('Max_RMS_current', 6, _validateraw=lambda x, ap: (0 <= x) & (x <= 255),
                                            _tophys=conv_current_to_phys,
                                            _toraw=conv_current_to_raw,
                                            depends=['top_rms_current'],
                                            rawminimum=0, rawmaximum=255, isinteger=False, storable=True,),
                            MotorParameter('Standby_RMS_current', 7, _validateraw=lambda x, ap: (0 <= x) & (x <= 255),
                                            _tophys=conv_current_to_phys,
                                            _toraw=conv_current_to_raw,
                                            rawminimum=0, rawmaximum=255, isinteger=False,
                                            depends=['top_rms_current'], storable=True),
                             MotorParameter('Right_limit_disable', 12, _validateraw=lambda x, ap: isinstance(x, bool), raw_is_phys=True, rawminimum=0, rawmaximum=1, isinteger=True, storable=True),
                             MotorParameter('Left_limit_disable', 13, _validateraw=lambda x, ap: isinstance(x, bool), raw_is_phys=True, rawminimum=0, rawmaximum=1, isinteger=True, storable=True),
                             MotorParameter('Freewheeling_delay', 204, _validateraw=lambda x, ap: (0 <= x) & (x <= 65535), raw_is_phys=True, rawminimum=0, rawmaximum=65535, isinteger=True, storable=True),
                             MotorParameter('Current_load', 206, readonly=True, raw_is_phys=True, isinteger=True),
                             MotorParameter('Current_speed', 3, _validateraw=lambda x, ap: (0 <= x) & (x <= 2047),
                                            _tophys=conv_speed_to_phys,
                                            _toraw=conv_speed_to_raw,
                                            depends=['f_clk', 'Pulse_div', 'Ustep_resol', 'step_to_cal'],
                                           rawminimum=0, rawmaximum=2047, isinteger=False,
                                            ),
                             MotorParameter('Current_position', 1, _validateraw=lambda x, ap: (ap['soft_left'] <= x) & (x <= ap['soft_right']),
                                            _tophys=conv_pos_to_phys,
                                            _toraw=conv_pos_to_raw,
                                            depends=['soft_left', 'soft_right', 'step_to_cal', 'Ustep_resol']),
                             MotorParameter('Target_position', 0, _validateraw=lambda x, ap: (ap['soft_left'] <= x) & (x <= ap['soft_right']),
                                            _tophys=conv_pos_to_phys,
                                            _toraw=conv_pos_to_raw,
                                            depends=['soft_left', 'soft_right', 'step_to_cal', 'Ustep_resol']),
                             MotorParameter('Ramp_mode', 138, _validateraw=lambda x, ap: (0 <= x) & (x <= 2), raw_is_phys=True, rawminimum=0, rawmaximum=2, isinteger=True, storable=False),
                             MotorParameter('step_to_cal', None, raw_is_phys=True),
                             MotorParameter('f_clk', None, readonly=True, raw_is_phys=True, rawminimum=0),
                             MotorParameter('soft_left', None, _tophys=conv_pos_to_phys, _toraw=conv_pos_to_raw),
                             MotorParameter('soft_right', None, _tophys=conv_pos_to_phys, _toraw=conv_pos_to_raw),
                             MotorParameter('backlash', None, _tophys=conv_pos_to_phys, _toraw=conv_pos_to_raw),
                             MotorParameter('top_rms_current', None, readonly=True),
                             MotorParameter('Left_limit_status', 11, _validateraw=lambda x, ap: isinstance(x, bool), readonly=True, raw_is_phys=True, rawminimum=0, rawmaximum=1, isinteger=True),
                             MotorParameter('Right_limit_status', 10, _validateraw=lambda x, ap: isinstance(x, bool), readonly=True, raw_is_phys=True, rawminimum=0, rawmaximum=1, isinteger=True),
                              ]



class TMCM351(TMCMModule):
    def _adjust_hwtype(self):
        self.max_peak_current = 4.0
        self.max_rms_current = 2.8
        self.n_axes = 3
        self.hwtype = 'TMCM351'
        self.stallGuardversion = 1
        self.coolstepenabled = False
        self.max_ustepresol = 6
        self.motor_params = COMMON_MOTOR_PARAMETERS + [
                                MotorParameter('Ustep_resol', 140, _validatephys=lambda x, ap:(0 <= x) & (x <= 6), raw_is_phys=True,
                                          rawminimum=0, rawmaximum=6, isinteger=True, storable=True),
                                MotorParameter('Mixed_decay_threshold', 203, _validateraw=lambda x, ap: (0 <= x) & (x <= 2048),
                                               _tophys=conv_speed_to_phys,
                                               _toraw=conv_speed_to_raw,
                                               depends=['f_clk', 'Pulse_div', 'Ustep_resol', 'step_to_cal'],
                                               rawminimum=0, rawmaximum=2047, isinteger=False, storable=True,
                                              ),
                                MotorParameter('Stallguard_threshold', 205, _validateraw=lambda x, ap: (0 <= x) & (x <= 7), storable=True,
                                               rawminimum=0, rawmaximum=7, raw_is_phys=True, isinteger=True),
                                MotorParameter('Fullstep_threshold', 211, _validateraw=lambda x, ap: (0 <= x) & (x <= 2047),
                                               _tophys=conv_speed_to_phys,
                                               _toraw=conv_speed_to_raw,
                                               depends=['f_clk', 'Pulse_div', 'Ustep_resol', 'step_to_cal'],
                                               rawminimum=0, rawmaximum=2047, isinteger=False, storable=True,
                                               ),
                                                       ]



class TMCM6110(TMCMModule):
    def _adjust_hwtype(self):
        self.max_peak_current = 1.6
        self.max_rms_current = 1.1
        self.n_axes = 6
        self.hwtype = 'TMCM6110'
        self.stallGuardversion = 2
        self.coolstepenabled = True
        self.max_ustepresol = 8
        self.motor_params = [MotorParameter('Ustep_resol', 140, _validatephys=lambda x, ap:(0 <= x) & (x <= 8), raw_is_phys=True,
                                          rawminimum=0, rawmaximum=8, isinteger=True, storable=True), ] + COMMON_MOTOR_PARAMETERS

class StepperMotor(GObject.GObject):
    __gsignals__ = {'motor-start':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'motor-report':(GObject.SignalFlags.RUN_FIRST, None, (float, float, float)),
                    'motor-stop':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'motor-limit':(GObject.SignalFlags.RUN_FIRST, None, (bool, bool)),
                    'settings-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'notify':'override',
                    'idle':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    }
    mot_idx = GObject.property(type=int, default=0, minimum=0, maximum=100, blurb='Motor index in TMCM module')
    alias = GObject.property(type=str, default='<unknown motor>', blurb='Mnemonic name')
    name = GObject.property(type=str, default='<unknown motor>', blurb='Standardized name')
    step_to_cal = GObject.property(type=float, default=1 / 200.0, blurb='Full step size in calibrated units')
    f_clk = GObject.property(type=int, default=16000000, blurb='TMCM clock frequency')
    softlimits = GObject.property(type=object, blurb='Software limits')
    status = GObject.property(type=str, default=StepperStatus.Disconnected, blurb='Status')
    backlash = GObject.property(type=float, default=0.2, blurb='Motor backlash')
    def __init__(self, driver, mot_idx, name=None, alias=None, step_to_cal=1 / 200.0, softlimits=(-float('inf'), float('inf')), f_clk=16000000, backlash=0.2):
        GObject.GObject.__init__(self)
        self._movequeue = []
        self.driver = weakref.ref(driver)
        if name is None:
            name = 'MOT_' + str(mot_idx + 1)
        if alias is None:
            alias = name
        self.name = name
        self.alias = alias
        self.mot_idx = mot_idx
        self._stateparams = {}
        self._stateparams['top_rms_current'] = self.driver().max_rms_current
        self._stateparams['f_clk'] = f_clk
        self.backlash = backlash
        self.f_clk = f_clk
        self._stateparams['step_to_cal'] = step_to_cal
        self.step_to_cal = step_to_cal
        self._stateparams['soft_left'] = min(softlimits)
        self._stateparams['soft_right'] = max(softlimits)
        self.softlimits = softlimits
        self._limitdata = None
        self.next_idle_position = None
        self.status = StepperStatus.Idle

    def get_parameter(self, name, raw=False, force_refresh=False):
        if (name not in self._stateparams) or force_refresh:
            self.reload_parameters(name)
        if raw:
            return self._stateparams[name]
        else:
            motpar = [m for m in self.driver().motor_params if m.name == name][0]
            for missing_dep in [p for p in motpar.depends if ((p not in self._stateparams) or force_refresh)]:
                self.reload_parameters(missing_dep)
            return motpar.to_phys(self._stateparams[name], self._stateparams)

    def set_parameter(self, name, value, raw=False):
        logger.debug('Motor '+self.alias+' set_parameter: '+name)
        motpar = [m for m in self.driver().motor_params if m.name == name][0]
        if motpar.readonly:
            raise MotorError('Attempted to set read-only parameter %s.' % name)
        for missing_dep in [p for p in motpar.depends if p not in self._stateparams]:
            self.reload_parameters(missing_dep)
        if raw:
            physval = motpar.to_phys(value, self._stateparams)
            rawval = value
        else:
            physval = value
            rawval = motpar.to_raw(value, self._stateparams)

        if not motpar.validate(physval, self._stateparams):
            logger.warning('Validation failed while setting parameter %s to %s.' % (motpar.name, str(value)))
            raise MotorError('Validation failed while setting parameter %s to %s.' % (motpar.name, str(value)))
        if motpar.axisparameter_idx is None:
            self._stateparams[name] = rawval
        else:
            self._stateparams[name] = self.driver().execute(5, motpar.axisparameter_idx, self.mot_idx, rawval)
        if name == 'soft_left':
            logger.debug('Motor '+self.alias+' Updating soft left limit to '+str(rawval)+' (raw)')
            self.softlimits = (rawval, max(self.softlimits))
        if name == 'soft_right':
            logger.debug('Motor '+self.alias+' Updating soft right limit to '+str(rawval)+' (raw)')
            self.softlimits = (min(self.softlimits), rawval)
        if name == 'step_to_cal':
            self.step_to_cal = value
        if name == 'backlash':
            self.backlash = value

    def do_notify(self, prop):
        logger.debug('Motor'+self.alias+' notify::'+prop.name)
        if prop.name in ['step_to_cal', 'f_clk', 'backlash']:
            self._stateparams[prop.name] = self.get_property(prop.name)
        elif prop.name == 'softlimits':
            self._stateparams['soft_left'] = min(self.softlimits)
            self._stateparams['soft_right'] = max(self.softlimits)
        if prop.name not in ['status']:
            self.emit('settings-changed')
        else:
            logger.debug('Motor property %s changed to: %s' % (prop.name, str(self.get_property(prop.name))))
        if prop.name == 'status':
            if self.status == StepperStatus.Idle:
                self.emit('idle')
    def do_settings_changed(self):
        self.driver().save_settings_delayed()

    def flush_queue(self):
        self._movequeue = []

    def _start_move(self):
        logger.debug(str(self) + ': _start_move()')
        if self.status == StepperStatus.Moving:
            # if we are already moving, do not start another move.
            return False
        if not self.driver()._motorsemaphore.acquire(False):
            # if too many motors are in motion, do not start.
            logger.debug('Cannot acquire semaphore.')
            return False
        # Warning: we now have acquired one semaphore. If for any
        # reason we cannot start the motion, we should release it.
        try:
            rawpos, relative = self._movequeue.pop()[:2]
        except IndexError:
            # if no motion commands are queued, return.
            self.driver()._motorsemaphore.release()
            logger.debug('_movequeue empty!')
            return False
        try:
            # Actually start the move.
            self.status = StepperStatus.Moving
            self.driver().execute(4, int(relative), self.mot_idx, rawpos)
            self.emit('motor-start')
        except:
            # could not start the move. This motion command is lost, we
            # release the semaphore and re-raise the exception
            self.driver()._motorsemaphore.release()
            if self._movequeue:
                self.status = StepperStatus.Queued
            else:
                self.status = StepperStatus.Idle
            raise
        return True

    def __del__(self):
        driver = self.driver()
        if driver is not None:
            try:
                del driver.motors[self.name]
            except KeyError:
                pass

    def check_limits(self):
        newlims = (self.get_parameter('Left_limit_status', force_refresh=True),
                   self.get_parameter('Right_limit_status', force_refresh=True))
        if self._limitdata is None or self._limitdata != newlims:
            self._limitdata = newlims
            self.emit('motor-limit', *self._limitdata)
        return True

    def do_motor_start(self):
        GLib.idle_add(self.motor_monitor)

    def do_motor_stop(self):
        self.driver()._motorsemaphore.release()
        self.driver().save_settings()
        if not self._movequeue:
            self.status = StepperStatus.Idle
        else:
            self.status = StepperStatus.Queued

    def get_softlimits_phys(self):
        return tuple(conv_pos_to_phys(x,self._stateparams) for x in self.softlimits)

    def motor_monitor(self):
        try:
            speed = self.get_parameter('Current_speed', force_refresh=True)
            load = self.get_parameter('Current_load', force_refresh=True)
            pos = self.get_parameter('Current_position', force_refresh=True)
            if (pos < self.get_parameter('soft_left')) or (pos > self.get_parameter('soft_right')):
                self.stop()
            self.check_limits()
            self.emit('motor-report', pos, speed, load)
            if speed != 0:
                return True
            else:
                self.emit('motor-stop')
                return False
        except Exception as exc:
            logger.critical('Exception swallowed in StepperMotor.motor_monitor(): ' + str(exc))
            return True

    def save_to_configparser(self, cp):
        if not self.driver().connected():
            return cp
        if cp.has_section(self.name):
            cp.remove_section(self.name)
        cp.add_section(self.name)
        pos = self.get_parameter('Current_position', raw=True)
        cp.set(self.name, 'Pos_raw', pos)
        cp.set(self.name, 'Alias', self.alias)
        cp.set(self.name, 'Idx', self.mot_idx)
        cp.set(self.name, 'Step_to_cal', self.step_to_cal)
        cp.set(self.name, 'F_CLK', self.f_clk)
        cp.set(self.name, 'Soft_left', self.softlimits[0])
        cp.set(self.name, 'Soft_right', self.softlimits[1])
        cp.set(self.name, 'Settings_changed_timeout', self.settingschanged_timeout)
        return cp

    def load_from_configparser(self, cp):
        if not cp.has_section(self.name):
            return
        if cp.has_option(self.name, 'Alias'):
            self.alias = cp.get(self.name, 'Alias')
        if cp.has_option(self.name, 'Idx'):
            self.mot_idx = cp.getint(self.name, 'Idx')
        if cp.has_option(self.name, 'Step_to_cal'):
            self.step_to_cal = cp.getfloat(self.name, 'Step_to_cal')
        if cp.has_option(self.name, 'F_CLK'):
            self.f_clk = cp.getint(self.name, 'F_CLK')
        if cp.has_option(self.name, 'Soft_left'):
            logger.debug('Loading softlimits.left from configparser')
            self.softlimits = (cp.getfloat(self.name, 'Soft_left'), self.softlimits[1])
            logger.debug('Motor '+self.alias+' soft limits are now: '+str(self.softlimits))
            logger.debug('Motor '+self.alias+' soft limits in _stateparams: '+str(self._stateparams['soft_left'])+', '+str(self._stateparams['soft_right']))
        if cp.has_option(self.name, 'Soft_right'):
            logger.debug('Loading softlimits.right from configparser')
            self.softlimits = (self.softlimits[0], cp.getfloat(self.name, 'Soft_right'))
            logger.debug('Motor '+self.alias+' soft limits are now: '+str(self.softlimits))
            logger.debug('Motor '+self.alias+' soft limits in _stateparams: '+str(self._stateparams['soft_left'])+', '+str(self._stateparams['soft_right']))
        if cp.has_option(self.name, 'Pos_raw'):
            if self.driver().connected():
                self.calibrate_pos(cp.getint(self.name, 'Pos_raw'), raw=True);
        if cp.has_option(self.name, 'Settings_changed_timeout'):
            self.settingschanged_timeout = cp.getfloat(self.name, 'Settings_changed_timeout')

    def reload_parameters(self, paramname=None):
        if paramname is not None:
            params = [p for p in self.driver().motor_params if p.name == paramname]
        else:
            params = self.driver().motor_params
        changed = False
        for par in params:
            if par.axisparameter_idx is None:
                continue
            newval = self.driver().execute(6, par.axisparameter_idx, self.mot_idx)
            if (par.name not in self._stateparams) or (newval != self._stateparams[par.name]):
                self._stateparams[par.name] = newval
                changed = True
        if changed:
            self.emit('settings-changed')

    def is_moving(self):
        return self.status in [ StepperStatus.Busy, StepperStatus.Moving]

    def stop(self):
        self.driver().execute(3, 0, self.mot_idx, 0)

    def moveto(self, pos, raw=False, relative=False):
        if not raw:
            pos = conv_pos_to_raw(pos, self._stateparams)
        # below this line, pos is in raw device units (microsteps)
        # determine the end position
        if relative:
            if self._movequeue:
                endpos = self._movequeue[-1][-1]
            else:
                endpos = self.get_parameter('Target_position', raw=True, force_refresh=True)
            newendpos = endpos + pos
        else:
            newendpos = pos
        # check if the end position of the motion is between the software limits.
        if (self.get_parameter('soft_left', raw=True) > newendpos) or (self.get_parameter('soft_right', raw=True) < newendpos):
            raise MotorError('Target of movement of motor %s is outside the software limits.' % str(self))
        # enqueue the motor movement command
        self._movequeue.insert(0, (pos, relative, newendpos))
        logger.debug('Queued movement command for motor %s: %s' % (str(self), str((pos, relative, newendpos))))
        if self.status == StepperStatus.Idle:
            self.status = StepperStatus.Queued
        # try to start the motion. If this cannot be accomplished (another motor is running),
        # the driver will call this again for us when we are on turn.
        self._start_move()

    def moverel(self, pos, raw=False):
        return self.moveto(self, pos, raw, True)

    def calibrate_pos(self, pos=0, raw=False):
        logger.debug('Motor '+self.alias+' calibrating.')
        if not raw:
            pos = conv_pos_to_raw(pos, self._stateparams)
        if (self.get_parameter('soft_left', raw=True) > pos) or (self.get_parameter('soft_right', raw=True) < pos):
            raise MotorError('Cannot calibrate outside software limits: %g <= %g <= %g is not true!' % (self.get_parameter('soft_left', raw=True),
                                                                                                        pos,
                                                                                                        self.get_parameter('soft_right', raw=True)))
        # set driver in velocity mode, since if we are in position mode, setting either the actual or the
        # target position will move the motor.
        self.set_parameter('Ramp_mode', 2)
        self.set_parameter('Current_position', pos, raw=True)
        logger.debug('Motor '+self.alias+' soft limits are now: '+str(self.softlimits))
        logger.debug('Motor '+self.alias+' soft limits in _stateparams: '+str(self._stateparams['soft_left'])+', '+str(self._stateparams['soft_right']))
        logger.debug('Setting target position to: %g <= %g <= %g'%(self._stateparams['soft_left'],pos,self._stateparams['soft_right']))
        self.set_parameter('Target_position', pos, raw=True)
        self.emit('settings-changed')

    def store_to_EEPROM(self):
        for motpar in [x for x in self.driver().motor_params if (x.axisparameter_idx is not None) and (x.storable)]:
            logger.debug('Storing axis parameter %s (# %d) to EEPROM.' % (motpar.name, motpar.axisparameter_idx))
            self.driver().execute(7, motpar.axisparameter_idx, self.mot_idx)

    def __str__(self):
        return self.name + ' (' + self.alias + ')'

    def to_NeXus(self):
        p = nxs.NXpositioner()
        p.name = self.alias
        p.description = self.name
        p.value = self.get_parameter('Current_position', raw=False)
        p.value.attrs['units'] = 'mm'
        p.raw_value = self.get_parameter('Current_position', raw=True)
        p.target_value = self.get_parameter('Target_position', raw=False)
        p.target_value.attrs['units'] = 'mm'
        p.tolerance = 0
        p.tolerance.attrs['units'] = 'mm'
        p.soft_limit_min = self.get_parameter('soft_left', raw=False)
        p.soft_limit_min.attrs['units'] = 'mm'
        p.soft_limit_max = self.get_parameter('soft_right', raw=False)
        p.soft_limit_max.attrs['units'] = 'mm'
        p.velocity = self.get_parameter('Current_speed', raw=False)
        p.velocity.attrs['units'] = 'mm s-1'
        p.acceleration_time = self.get_parameter('Max_speed', raw=False) / self.get_parameter('Max_accel', raw=False)
        p.acceleration_time.attrs['units'] = 's'
        return p

    def update_NeXus(self, nxpositioner):
        nxpositioner.value = self.get_parameter('Current_position', raw=False)
        nxpositioner.raw_value = self.get_parameter('Current_position', raw=True)
        nxpositioner.target_value = self.get_parameter('Target_position', raw=False)
        nxpositioner.soft_limit_min = self.get_parameter('soft_left', raw=False)
        nxpositioner.soft_limit_max = self.get_parameter('soft_right', raw=False)
        nxpositioner.velocity = self.get_parameter('Current_speed', raw=False)
        nxpositioner.acceleration_time = self.get_parameter('Max_speed', raw=False) / self.get_parameter('Max_accel', raw=False)
        return nxpositioner
