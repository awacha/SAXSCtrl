import serial
import logging
import time
import struct
import multiprocessing
import multiprocessing.queues
import threading
import os
import socket
import select
import weakref
import ConfigParser
import numbers
from gi.repository import GObject
from gi.repository import GLib

from .instrument import Instrument_TCP, InstrumentError, InstrumentStatus, ConnectionBrokenError
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class MotorError(InstrumentError):
    pass

class TMCMModuleStatus(InstrumentStatus):
    Moving = 'moving'
    Queued = 'queued'

class StepperStatus(InstrumentStatus):
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
    _motor_counter = 1
    def __init__(self, offline=True):
        self.motors = {}
        self.f_clk = 16000000
        self._adjust_hwtype()
        Instrument_TCP.__init__(self, offline)
        self.timeout = 0.1
        self.timeout2 = 0.1
        self.recvbufsize = 8
        self.port = 2001
        self.cmdqueue = multiprocessing.queues.Queue()
    def _adjust_hwtype(self):
        raise NotImplementedError('Unknown TMCM type: ' + hwtype)
    def _post_connect(self):
        GLib.idle_add(self._check_queue)
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
    def motorstop(self, flushqueue=True):
        if flushqueue:
            self._flush_queue()
        for m in self.moving():
            m.stop()
    def __del__(self):
        for m in self.motors.keys():
            del self.motors[m]
    def save_settings(self, filename=None):
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
                    mot = self.add_motor(0, name)
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
            raise MotorError('Wrong checksum of sent message')
        elif status == 2:
            raise MotorError('Invalid command')
        elif status == 3:
            raise MotorError('Wrong type')
        elif status == 4:
            raise MotorError('Invalid value')
        elif status == 5:
            raise MotorError('Configuration EEPROM locked')
        elif status == 6:
            raise MotorError('Command not available')
        value = struct.unpack('>i', message[4:8])[0]
        if status != 100:
            raise MotorError('Status not OK!')
        return value
    def execute(self, instruction, type_=0, mot_bank=0, value=0):
        if instruction is not None:
            cmd = (1, instruction, type_, mot_bank) + struct.unpack('4B', struct.pack('>i', int(value)))
            cmd = cmd + (sum(cmd) % 256,)
            # logger.debug('About to send TMCL command: ' + ''.join(('%02x' % x) for x in cmd))
            cmd = ''.join(chr(x) for x in cmd)
        else:
            cmd = None
        # logger.debug('Sending message to TMCM module: 0x' + ''.join('%x' % ord(x) for x in cmd))
        for i in reversed(range(self.send_recv_retries)):  # self.send_recv_retries-1 to 0.
            try:
                result = self.send_and_receive(cmd, True)
                value = self.interpret_message(result, instruction)
                break
            except MotorError as exc:
                if not i:  # all retries exhausted
                    raise exc
                logger.warning('Communication error: ' + exc.message + '(type: ' + str(type(exc)) + '); retrying (%d retries left)' % i)
            except (ConnectionBrokenError, InstrumentError) as exc:
                logger.error('Connection of instrument %s broken: ' % self._get_classname() + exc.message)
                raise MotorError('Connection broken: ' + exc.message)
            except Exception as exc:
                logger.error('Instrument error on module %s: ' % self.hwtype + exc.message)
                raise MotorError('Instrument error: ' + exc.message)
            
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
        return [m for m in self.motors if self.motors[m].is_moving()]
    def get_motor(self, idx):
        if isinstance(idx, numbers.Number):
            return [self.motors[m] for m in self.motors if self.motors[m].mot_idx == idx][0]
        elif isinstance(idx, basestring):
            return [self.motors[m] for m in self.motors if (self.motors[m].name == idx) or (self.motors[m].alias == idx) or (str(self.motors[m]) == idx) ][0]
        else:
            raise NotImplementedError('Invalid type for parameter idx: ', type(idx))
    def do_motor_stop(self, mot):
        # a motor movement is finished, re-register the queue checking idle handler.
        self.status = TMCMModuleStatus.Busy
        GLib.idle_add(self._check_queue)
    def _movemotor(self, idx, pos, raw=False, relative=False, queued=True):
        logger.debug('_movemotor was called with idx=%d, pos=%d, raw=%s, relative=%s' % (idx, pos, raw, relative))
        motor = self.get_motor(idx)
        logger.debug('Motor name is: ' + motor.name)
        if not raw:
            physpos = pos
            pos = motor.conv_pos_raw(pos)
        else:
            physpos = motor.conv_pos_phys(pos)
        if motor.next_idle_position is None:
            motor.next_idle_position = motor.get_pos()
        logger.debug('physpos: %g; pos: %g; next_idle_pos: %g.' % (physpos, pos, motor.next_idle_position))
        if self.moving() and not queued:
            raise MotorError('Cannot move motor %s: A motor is currently moving.' % motor.name)
        if relative:
            absphyspos = physpos + motor.next_idle_position
        else:
            absphyspos = physpos
        logger.debug('absphyspos: %g' % absphyspos)
        if (min(motor.softlimits) > absphyspos) or (absphyspos > max(motor.softlimits)):
            raise MotorError('Target position outside software limits')
        # update the next idle position of the current motor.
        motor.next_idle_position = absphyspos
        logger.debug('Queueing movement: %d, %g, %s' % (idx, pos, relative))
        if self.status == TMCMModuleStatus.Idle:
            self.status = TMCMModuleStatus.Busy
        self.cmdqueue.put((idx, pos, relative))
    def _do_move(self, idx, rawpos, relative):
        logger.debug('Do-move: %d, %g, %s' % (idx, rawpos, relative))
        motor = self.get_motor(idx)
        moving = self.moving()
        if moving and motor.name not in moving:
            raise MotorError('Another motor is currently moving.')
        motor.emit('motor-start')
        self.execute(4, int(relative), idx, rawpos)
    def do_idle(self):
        pass
    def _check_queue(self):
        if not self.connected():
            # if the motor controller is not connected (or has been disconnected),
            # unregister this idle handle by returning False.
            return False
        try:
            idx, rawpos, relative = self.cmdqueue.get_nowait()
        except multiprocessing.queues.Empty:
            # the queue is empty. We return True, so our idle handler will not be
            # unregistered.
            if self.status != TMCMModuleStatus.Idle:
                self.status = TMCMModuleStatus.Idle
            return True
        # if we reach here, we have a job to do.
        self.status = TMCMModuleStatus.Moving
        self._do_move(idx, rawpos, relative)
        # now we unregister (!) our handle, since while the motor runs, there is
        # no point for checking new queued commands. The motor will emit a 
        # "motor-stop" signal at the end, we will use that occasion to re-register
        # our idle handler.
        return False
    def _flush_queue():
        """Flush the command queue."""
        while True:
            try:
                self.cmdqueue.get_nowait()
            except multiprocessing.queues.Empty:
                break
    def get_current_parameters(self):
        dic = {}
        for m in self.motors.values():
            dic[m.alias] = m.get_pos()
        return dic
    def do_notify(self, prop):
        Instrument_TCP.do_notify(self, prop)
        if prop.name == 'configfile':
            try:
                self.load_settings(self.configfile)
            except Exception as exc:
                logger.error('Error while calling TMCMModule.load_settings() from do_notify: ' + exc.message)

class TMCM351(TMCMModule):
    def _adjust_hwtype(self):
        self.max_peak_current = 4.0
        self.max_rms_current = 2.8
        self.n_axes = 3
        self.hwtype = 'TMCM351'
        self.stallGuardversion = 1
        self.coolstepenabled = False
        self.max_ustepresol = 6
        self.motor_params = [('Max_speed', 4), ('Max_accel', 5), ('Max_current', 6), ('Standby_current', 7),
                  ('Right_limit_disable', 12), ('Left_limit_disable', 13), ('Ustep_resol', 140),
                  ('Ramp_div', 153), ('Pulse_div', 154),  # ('Mixed_decay_threshold', 203),
                  ('Freewheeling_delay', 204), ]  # ('Stallguard_threshold', 205), ('Fullstep_threshold', 211)]

class TMCM6110(TMCMModule):
    def _adjust_hwtype(self):
        self.max_peak_current = 1.6
        self.max_rms_current = 1.1
        self.n_axes = 6
        self.hwtype = 'TMCM6110'
        self.stallGuardversion = 2
        self.coolstepenabled = True
        self.max_ustepresol = 8
        self.motor_params = [('Max_speed', 4), ('Max_accel', 5), ('Max_current', 6), ('Standby_current', 7),
                  ('Right_limit_disable', 12), ('Left_limit_disable', 13), ('Ustep_resol', 140),
                  ('Ramp_div', 153), ('Pulse_div', 154),
                  ('Freewheeling_delay', 204)]
    
# class TMCMModule_RS232(TMCMModule):
#     def __init__(self, serial_device, timeout=1, settingsfile=None, settingssaveinterval=10):
#         TMCMModule.__init__(self, settingsfile, settingssaveinterval)
#         self.rs232 = serial.Serial(serial_device)
#         if not self.rs232.isOpen():
#             raise MotorError('Cannot open RS-232 port ' + str(serial_device))
#         self.rs232.timeout = timeout
#         self.rs232.flushInput()
#         self.load_settings()
#         self.emit('connect-equipment')
#     def connected(self):
#         return self.rs232 is not None and self.rs232.isOpen()
#     def do_communication(self, cmd):
#         with self.comm_lock:
#             if cmd is not None:
#                 self.rs232.write(cmd)
#             result = self.rs232.read(9)
#             self.rs232.flushInput()
#         if not result and cmd is not None:
#             self.rs232.close()
#             self.rs232 = None
#             self.emit('disconnect-equipment')
#             raise MotorError('Communication error. Controller may not be connected')
#         return result

                
class StepperMotor(GObject.GObject):
    __gsignals__ = {'motor-start':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'motor-report':(GObject.SignalFlags.RUN_FIRST, None, (float, float, float)),
                    'motor-stop':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'motor-limit':(GObject.SignalFlags.RUN_FIRST, None, (bool, bool)),
                    'settings-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'notify':'override'
                    }
    mot_idx = GObject.property(type=int, default=0, minimum=0, maximum=100, blurb='Motor index in TMCM module')
    alias = GObject.property(type=str, default='<unknown motor>', blurb='Mnemonic name')
    name = GObject.property(type=str, default='<unknown motor>', blurb='Standardized name')
    step_to_cal = GObject.property(type=float, default=1 / 200.0, blurb='Microstep size in calibrated units')
    f_clk = GObject.property(type=int, default=16000000, blurb='TMCM clock frequency')
    softlimits = GObject.property(type=object, blurb='Software limits')
    settings_timeout = GObject.property(type=float, default=60, blurb='Settings timeout')
    status = GObject.property(type=str, default=StepperStatus.Disconnected, blurb='Status')
    def __init__(self, driver, mot_idx, name=None, alias=None, step_to_cal=1 / 200.0, softlimits=(-float('inf'), float('inf')), f_clk=16000000):
        GObject.GObject.__init__(self)
        self.driver = weakref.ref(driver)
        if name is None:
            name = 'MOT_' + str(mot_idx + 1)
        if alias is None:
            alias = name
        self.name = name
        self.alias = alias
        self.mot_idx = mot_idx
        self.settings = {}
        self.step_to_cal = step_to_cal
        self.f_clk = f_clk
        self.softlimits = softlimits
        self.limitdata = None
        self.next_idle_position = None
        self.status = StepperStatus.Idle
        self._circumstances = {}
    def do_notify(self, prop):
        if prop.name not in ['status']:
            self.emit('settings-changed')
        else:
            logger.debug('Motor property %s changed to: %s' % (prop.name, str(self.get_property(prop.name))))
    def do_settings_changed(self):
        self.driver().save_settings()
    def __del__(self):
        if self.limit_check is not None:
            GObject.source_remove(self.limit_check)
            self.limit_check = None
        driver = self.driver()
        if driver is not None:
            del driver.motors[self.name]
    def check_limits(self):
        newlims = (self.get_left_limit(), self.get_right_limit())
        if self.limitdata is None or self.limitdata != newlims:
            self.limitdata = newlims
            self.emit('motor-limit', *self.limitdata)
        return True
    def do_motor_start(self):
        GLib.idle_add(self.motor_monitor)
        self.status = StepperStatus.Busy
    def do_motor_stop(self):
        self.status = StepperStatus.Idle
        self._circumstances = {}
        self.driver().save_settings()
    def motor_monitor(self):
        try:
            speed = self.get_speed()
            load = self.get_load()
            pos = self.get_pos()
            if (min(self.softlimits) > pos) or (max(self.softlimits) < pos):
                self.stop()
            self.check_limits()
            self.emit('motor-report', pos, speed, load)
            if speed != 0:
                return True
            else:
                self.emit('motor-stop')
                return False
        except Exception as exc:
            logger.critical('Exception swallowed in StepperMotor.motor_monitor(): ' + exc.message)
            return True
    def save_to_configparser(self, cp):
        if cp.has_section(self.name):
            cp.remove_section(self.name)
        cp.add_section(self.name)
        pos = self.get_pos(raw=True)
        cp.set(self.name, 'Pos_raw', pos)
        cp.set(self.name, 'Alias', self.alias)
        cp.set(self.name, 'Idx', self.mot_idx)
        cp.set(self.name, 'Step_to_cal', self.step_to_cal)
        cp.set(self.name, 'F_CLK', self.f_clk)
        cp.set(self.name, 'Soft_left', self.softlimits[0])
        cp.set(self.name, 'Soft_right', self.softlimits[1])
        cp.set(self.name, 'Settings_timeout', self.settings_timeout)
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
            self.softlimits = (cp.getfloat(self.name, 'Soft_left'), self.softlimits[1])
        if cp.has_option(self.name, 'Soft_right'):
            self.softlimits = (self.softlimits[0], cp.getfloat(self.name, 'Soft_right'))
        if cp.has_option(self.name, 'Pos_raw'):
            if self.driver().connected():
                self.calibrate_pos(cp.getint(self.name, 'Pos_raw'), raw=True);
        if cp.has_option(self.name, 'Settings_timeout'):
            self.settings_timeout = cp.getfloat(self.name, 'Settings_timeout')
    def refresh_settings(self, paramname=None):
        logger.debug('Refresh_settings on motor ' + self.alias)
        if paramname is not None:
            params = [p for p in self.driver().motor_params if p[0] == paramname]
        else:
            params = self.driver().motor_params
        changed = False
        for name, idx in params:
            newval = self.driver().execute(6, idx, self.mot_idx)
            if name not in self.settings or newval != self.settings[name]:
                self.settings[name] = newval
                changed = True
        self.settings['__timestamp__'] = time.time()
        self.emit('settings-changed') 
    def get_load(self):
        if (self.status == StepperStatus.Busy) or ('load' not in self._circumstances):
            self._circumstances['load'] = self.driver().execute(6, 206, self.mot_idx)
        return self._circumstances['load']
    def get_accel(self, raw=False):
        if self.status != StepperStatus.Busy:
            return 0
        val = self.driver().execute(6, 135, self.mot_idx)
        if raw:
            return val
        else:
            return self.conv_accel_phys(val)
    def get_left_limit(self):
        if (self.status == StepperStatus.Busy) or ('leftlimit' not in self._circumstances):
            self._circumstances['leftlimit'] = bool(self.driver().execute(6, 11, self.mot_idx)) 
        return self._circumstances['leftlimit']
        
    def get_right_limit(self):
        if (self.status == StepperStatus.Busy) or ('rightlimit' not in self._circumstances):
            self._circumstances['rightlimit'] = bool(self.driver().execute(6, 10, self.mot_idx)) 
        return self._circumstances['rightlimit']
    def get_target_reached(self):
        return bool(self.driver().execute(6, 8, self.mot_idx))
    def get_speed(self, raw=False):
        if (self.status != StepperStatus.Busy):
            return 0
        val = self.driver().execute(6, 3, self.mot_idx)
        if raw:
            return val
        else:
            return self.conv_speed_phys(val)
    def set_speed(self, speed, raw=False):
        moving = self.driver().moving()
        if moving and self.name not in moving:
            raise MotorError('Another motor is currently moving.')
        if not raw:
            speed = self.conv_speed_raw(speed)
        if speed == 0:
            self.stop()
        elif speed < 0:
            self.emit('motor-start')
            self.rot_left(-speed)
        else:
            self.emit('motor-start')
            self.rot_right(speed)
    def is_moving(self):
        return self.get_speed(raw=True) != 0
    def get_target_pos(self, raw=False):
        if (self.status == StepperStatus.Busy) or ('targetpos' not in self._circumstances):
            self._circumstances['targetpos'] = self.driver().execute(6, 0, self.mot_idx)
        val = self._circumstances['targetpos']
        if raw:
            return val
        else:
            return self.conv_pos_phys(val)
    def set_target_pos(self, pos, raw=False):
        if not raw:
            pos = self.conv_pos_raw(pos)
        return self.driver().execute(5, 0, self.mot_idx, pos)
    def get_pos(self, raw=False):
        if (self.status == StepperStatus.Busy) or ('currpos' not in self._circumstances):
            self._circumstances['currpos'] = self.driver().execute(6, 1, self.mot_idx)
        val = self._circumstances['currpos']
        if raw:
            return val
        else:
            return self.conv_pos_phys(val)
    def set_pos(self, pos, raw=False):
        if not raw:
            pos = self.conv_pos_raw(pos)
        return self.driver().execute(5, 1, self.mot_idx, pos)
    def get_max_speed(self, raw=False):
        val = self.get_settings('Max_speed')
        if raw:
            return val
        else:
            return self.conv_speed_phys(val)
    def set_max_speed(self, maxspeed, make_default=False, raw=False):
        if not raw:
            maxspeed = self.conv_speed_raw(maxspeed)
        self.driver().execute(5, 4, self.mot_idx, maxspeed)
        if make_default:
            self.driver().execute(7, 4, self.mot_idx)
        self.refresh_settings('Max_speed')
    def get_max_accel(self, raw=False):
        val = self.get_settings('Max_accel')
        if raw:
            return val
        else:
            return self.conv_accel_phys(val)
    def set_max_accel(self, maxaccel, make_default=False, raw=False):
        if not raw:
            maxaccel = self.conv_accel_raw(maxaccel)
        self.driver().execute(5, 5, self.mot_idx, maxaccel)
        if make_default:
            self.driver().execute(7, 5, self.mot_idx)
        self.refresh_settings('Max_accel')
    def get_max_peak_current(self):
        return (self.get_settings('Max_current') * self.driver().max_peak_current) / 255
    def set_max_peak_current(self, Ipeak, make_default=False):
        self.driver().execute(5, 6, self.mot_idx, (Ipeak * 255) / self.driver().max_peak_current)
        if make_default:
            self.driver().execute(7, 6, self.mot_idx)
        self.refresh_settings('Max_current')
    def get_max_raw_current(self):
        return self.get_settings('Max_current')
    def set_max_raw_current(self, I, make_default=False):
        self.driver().execute(5, 6, self.mot_idx, I)
        if make_default:
            self.driver().execute(7, 6, self.mot_idx)
        self.refresh_settings('Max_current')
    def get_max_rms_current(self):
        return (self.get_settings('Max_current') * self.driver().max_rms_current) / 255
    def set_max_rms_current(self, Irms, make_default=False):
        self.driver().execute(5, 6, self.mot_idx, (Irms * 255) / self.driver().max_rms_current)
        if make_default:
            self.driver().execute(7, 6, self.mot_idx)
        self.refresh_settings('Max_current')
    def get_standby_peak_current(self):
        return (self.get_settings('Standby_current') * self.driver().max_peak_current) / 255
    def set_standby_peak_current(self, Ipeak, make_default=False):
        self.driver().execute(5, 7, self.mot_idx, (Ipeak * 255) / self.driver().max_peak_current)
        if make_default:
            self.driver().execute(7, 7, self.mot_idx)
        self.refresh_settings('Standby_current')
    def get_standby_raw_current(self):
        return (self.get_settings('Standby_current'))
    def set_standby_raw_current(self, I, make_default=False):
        self.driver().execute(5, 7, self.mot_idx, I)
        if make_default:
            self.driver().execute(7, 7, self.mot_idx)
        self.refresh_settings('Standby_current')
    def get_standby_rms_current(self):
        return (self.get_settings('Standby_current') * self.driver().max_rms_current) / 255
    def set_standby_rms_current(self, Irms, make_default=False):
        self.driver().execute(5, 7, self.mot_idx, (Irms * 255) / self.driver().max_rms_current)
        if make_default:
            self.driver().execute(7, 7, self.mot_idx)
        self.refresh_settings('Standby_current')
    def get_right_limit_disable(self):
        return self.get_settings('Right_limit_disable')
    def set_right_limit_disable(self, disabled, make_default=False):
        self.driver().execute(5, 12, self.mot_idx, disabled)
        if make_default:
            self.driver().execute(7, 12, self.mot_idx)
        self.refresh_settings('Right_limit_disable')
    def get_left_limit_disable(self):
        return self.get_settings('Left_limit_disable')
    def set_left_limit_disable(self, disabled, make_default=False):
        self.driver().execute(5, 13, self.mot_idx, disabled)
        if make_default:
            self.driver().execute(7, 13, self.mot_idx)
        self.refresh_settings('Left_limit_disable')
    def get_ustep_resolution(self):
        return self.get_settings('Ustep_resol')
    def set_ustep_resolution(self, usrs, make_default=False):
        """Set microstep resolution.
        
        The number of microsteps is 2**usrs.
        
        usrs can be 0 to 6 (inclusive).
        """
        self.driver().execute(5, 140, self.mot_idx, usrs)
        if make_default:
            self.driver().execute(7, 140, self.mot_idx)
        self.refresh_settings('Ustep_resol')
    def get_ramp_div(self):
        return self.get_settings('Ramp_div')
    def set_ramp_div(self, ramp_div, make_default=False):
        self.driver().execute(5, 153, self.mot_idx, ramp_div)
        if make_default:
            self.driver().execute(7, 153, self.mot_idx)
        self.refresh_settings('Ramp_div')
    def get_pulse_div(self):
        return self.get_settings('Pulse_div')
    def set_pulse_div(self, pulse_div, make_default=False):
        self.driver().execute(5, 154, self.mot_idx, pulse_div)
        if make_default:
            self.driver().execute(7, 154, self.mot_idx)
        self.refresh_settings('Pulse_div')
    def get_mixed_decay_threshold(self):
        return self.get_settings('Mixed_decay_threshold')
    def set_mixed_decay_threshold(self, mdt, make_default=False):
        self.driver().execute(5, 203, self.mot_idx, mdt)
        if make_default:
            self.driver().execute(7, 203, self.mot_idx)
        self.refresh_settings('Mixed_decay_threshold')
    def get_freewheeling_delay(self):
        return self.get_settings('Freewheeling_delay')
    def set_freewheeling_delay(self, fwd, make_default=False):
        self.driver().execute(5, 204, self.mot_idx, fwd)
        if make_default:
            self.driver().execute(7, 204, self.mot_idx)
        self.refresh_settings('Freewheeling_delay')
    def get_stallguard_threshold(self):
        return self.get_settings('Stallguard_threshold')
    def set_stallguard_threshold(self, sgt, make_default=False):
        self.driver().execute(5, 205, self.mot_idx, sgt)
        if make_default:
            self.driver().execute(7, 205, self.mot_idx)
        self.refresh_settings('Stallguard_threshold')
    def get_fullstep_threshold(self):
        return self.get_settings('Fullstep_threshold')
    def set_fullstep_threshold(self, fst, make_default=False):
        self.driver().execute(5, 211, self.mot_idx, fst)
        if make_default:
            self.driver().execute(7, 211, self.mot_idx)
        self.refresh_settings('Fullstep_threshold')
    def conv_speed_raw(self, speed_phys):
        settings = self.get_settings()
        return (speed_phys * 2 ** settings['Pulse_div'] * 2048.0 * 32 * 2 ** settings['Ustep_resol'] / (self.step_to_cal * self.f_clk))
    def conv_speed_phys(self, speed_raw):
        settings = self.get_settings()
        return self.step_to_cal * speed_raw * self.f_clk / (2 ** settings['Pulse_div'] * 2048.0 * 32 * 2 ** settings['Ustep_resol'])
    def conv_pos_raw(self, pos_phys):
        settings = self.get_settings()
        return (pos_phys / self.step_to_cal * 2 ** settings['Ustep_resol'])
    def conv_pos_phys(self, pos_raw):
        settings = self.get_settings()
        return pos_raw * self.step_to_cal / 2 ** settings['Ustep_resol']
    def conv_accel_raw(self, accel_phys):
        settings = self.get_settings()
        return (accel_phys / (self.f_clk ** 2 * self.step_to_cal) * (2 ** (settings['Pulse_div'] + settings['Ramp_div'] + 29) * 2 ** settings['Ustep_resol'])) 
    def conv_accel_phys(self, accel_raw):
        settings = self.get_settings()
        return self.f_clk ** 2 * accel_raw / (2 ** (settings['Pulse_div'] + settings['Ramp_div'] + 29)) * (self.step_to_cal / 2 ** settings['Ustep_resol']) 
    def rot_left(self, speed):
        moving = self.driver().moving()
        if moving and self.name not in moving:
            raise MotorError('Another motor is currently moving.')
        self.emit('motor-start')
        self.driver().execute(2, 0, self.mot_idx, speed)
    def rot_right(self, speed):
        moving = self.driver().moving()
        if moving and self.name not in moving:
            raise MotorError('Another motor is currently moving.')
        self.emit('motor-start')
        self.driver().execute(1, 0, self.mot_idx, speed)
    def stop(self):
        self.driver().execute(3, 0, self.mot_idx, 0)
    def moveto(self, pos, raw=False):
        self.driver()._movemotor(self.mot_idx, pos, raw, relative=False)
    def moverel(self, pos, raw=False):
        self.driver()._movemotor(self.mot_idx, pos, raw, relative=True)
    def get_settings(self, paramname=None):
        if not self.settings or ((self.settings_timeout > 0) and (self.settings['__timestamp__'] < time.time() - self.settings_timeout)):
            self.refresh_settings()
        if paramname is None:
            return self.settings
        elif paramname in self.settings:
            return self.settings[paramname]
        else:
            raise MotorError('Motor parameter %s not supported by the controller module %s. ' % (paramname, self.driver().hwtype))
    def calibrate_pos(self, pos=0, raw=False):
        for k in ['currpos', 'targetpos']:
            try:
                del self._circumstances[k]
            except KeyError:
                pass
        if not raw:
            physpos = pos
            pos = self.conv_pos_raw(pos)
        else:
            physpos = self.conv_pos_phys(pos)
        if (min(self.softlimits) > physpos) or (physpos > max(self.softlimits)):
            raise MotorError('Cannot calibrate outside software limits')
        # set driver in velocity mode, since if we are in position mode, setting either the actual or the
        # target position will move the motor.
        self.driver().execute(5, 138, self.mot_idx, 2)
        self.set_pos(pos, raw=True)
        self.set_target_pos(pos, raw=True)
        self.emit('settings-changed')
    def store_to_EEPROM(self):
        for idx in [4, 5, 6, 7, 12, 13, 140, 153, 154, 203, 204, 205, 211]:
            self.driver().execute(7, idx, self.mot_idx)
    def __str__(self):
        return self.name + ' (' + self.alias + ')'
