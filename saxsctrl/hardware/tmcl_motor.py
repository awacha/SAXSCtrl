import serial
import logging
import time
import struct
import multiprocessing
import threading
import os
import socket
import select
import weakref
import ConfigParser
from gi.repository import GObject

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class MotorError(StandardError):
    pass

class TMCM351(GObject.GObject):
    __gsignals__ = {'motors-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'connect-equipment':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'disconnect-equipment':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'motor-start':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'motor-report':(GObject.SignalFlags.RUN_FIRST, None, (object, float, float, float)),
                    'motor-stop':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'motor-limit':(GObject.SignalFlags.RUN_FIRST, None, (object, bool, bool)),
                    'motor-settings-changed':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    }
    def __init__(self, settingsfile=None, settingssaveinterval=10):
        GObject.GObject.__init__(self)
        self.comm_lock = multiprocessing.Lock()
        self.motors = {}
        self.f_clk = 16000000
        self.settingsfile = settingsfile
        self.settingsfile_in_use = False
    def connected(self):
        return False
    def __del__(self):
        for m in self.motors.keys():
            del self.motors[m]
    def save_settings(self, filename=None):
        if self.settingsfile_in_use:
            return
        self.settingsfile_in_use = True
        try:
            if filename is None:
                filename = self.settingsfile
            if filename is None:
                return
            cp = ConfigParser.ConfigParser()
            cp.read(filename)
            for m in self.motors:
                self.motors[m].save_to_configparser(cp)
            with open(filename, 'w') as f:
                cp.write(f)
            print "Saved TMCM351 settings to " + filename
            return True
        finally:
            self.settingsfile_in_use = False
    def load_settings(self, filename=None):
        if self.settingsfile_in_use:
            return
        self.settingsfile_in_use = True
        try:
            if filename is None:
                filename = self.settingsfile
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
            self.settingsfile_in_use = False
    def do_communication(self, cmd):
        raise NotImplementedError
    def send_and_recv(self, instruction=None, type_=0, mot_bank=0, value=0):
        if instruction is not None:
            cmd = (1, instruction, type_, mot_bank) + struct.unpack('4B', struct.pack('>i', int(value)))
            cmd = cmd + (sum(cmd) % 256,)
            logger.debug('About to send TMCL command: ' + ''.join(hex(x) for x in cmd))
            cmd = ''.join(chr(x) for x in cmd)
        else:
            cmd = None
        result = self.do_communication(cmd)
        if len(result) == 0:
            return 0, None
        logger.debug('Got TMCL result: ' + ''.join(hex(ord(x)) for x in result))
        # validate checksum
        if not (sum(ord(x) for x in result[:-1]) % 256 == ord(result[-1])):
            raise MotorError('Checksum error on received data!')
        if not ord(result[3]) == instruction:
            raise MotorError('Invalid reply from TMCM module: not the same instruction.')
        status = ord(result[2])
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
        value = struct.unpack('>i', result[4:8])[0]
        return status, value
    def execute(self, instruction, type_=0, mot_bank=0, value=0):
        status, value = self.send_and_recv(instruction, type_, mot_bank, value)
        if status != 100:
            raise MotorError('Status not OK!')
        return value
    def get_version(self):
        stat, ver = self.send_and_recv(136, 1)
        if ver / 0x10000 != 0x015f:
            raise MotorError('Invalid version signature: ' + hex(ver / 0x10000))
        ver = ver % 0x10000
        major = ver / 0x100
        minor = ver % 0x100
        return major, minor
    def add_motor(self, mot_idx, name=None, alias=None, step_to_cal=1 / 200.0, softlimits=(-float('inf'), float('inf'))):
        mot = StepperMotor(self, mot_idx, name, alias, step_to_cal, softlimits, self.f_clk)
        mot.connect('motor-start', lambda m:self.emit('motor-start', m))
        mot.connect('motor-report', lambda m, pos, speed, load: self.emit('motor-report', m, pos, speed, load))
        mot.connect('motor-stop', lambda m:self.emit('motor-stop', m))
        mot.connect('motor-limit', lambda m, left, right:self.emit('motor-limit', m, left, right))
        mot.connect('settings-changed', lambda m:self.emit('motor-settings-changed', m))
        self.emit('motors-changed')
        return mot
    def moving(self):
        """Return currently moving motors"""
        return [m for m in self.motors if self.motors[m].is_moving()]
    def get_motor(self, idx):
        return [self.motors[m] for m in self.motors if self.motors[m].mot_idx == idx][0]
    def moveto_motor(self, idx, pos):
        self.execute(4, 0, idx, pos)
        self.execute(138, 0, 0, 2 ** idx)
        GObject.idle_add(self._wait_for_targetreachedevent)
    def moverel_motor(self, idx, pos):
        self.execute(4, 1, idx, pos)
        self.execute(138, 0, 0, 2 ** idx)
    def _wait_for_targetreachedevent(self):
        status, value = self.send_and_recv(None)
        if value is not None:
            for idx in range(3):
                if value & 2 ** idx:
                    self.get_motor(idx).emit('motor-stop')
            return False
        return True
    
class TMCM351_RS232(TMCM351):
    def __init__(self, serial_device, timeout=1, settingsfile=None, settingssaveinterval=10):
        TMCM351.__init__(self, settingsfile, settingssaveinterval)
        self.rs232 = serial.Serial(serial_device)
        if not self.rs232.isOpen():
            raise MotorError('Cannot open RS-232 port ' + str(serial_device))
        self.rs232.timeout = timeout
        self.rs232.flushInput()
        self.load_settings()
    def connected(self):
        return self.rs232 is not None and self.rs232.isOpen()
    def do_communication(self, cmd):
        with self.comm_lock:
            if cmd is not None:
                self.rs232.write(cmd)
            result = self.rs232.read(9)
            self.rs232.flushInput()
        if not result and cmd is not None:
            self.rs232.close()
            self.rs232 = None
            self.emit('disconnect-equipment')
            raise MotorError('Communication error. Controller may not be connected')
        return result

class TMCM351_TCP(TMCM351):
    def __init__(self, host=None, port=2001, timeout=1, settingsfile=None):
        TMCM351.__init__(self, settingsfile)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket = None
        if self.host is not None:
            self.connect_to_controller()
    def connected(self):
        return self.socket is not None
    def connect_to_controller(self):
        if self.connected():
            raise MotorError('Already connected.')
        logger.debug('Connecting to TCP/RS232 converter.')
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ip = socket.gethostbyname(self.host)
            self.socket.connect((ip, self.port))
        except socket.gaierror:
            self.socket = None
            raise MotorError('Cannot resolve host name.')
        except socket.error:
            self.socket = None
            raise MotorError('Cannot connect to server.')
        self.socket.settimeout(self.timeout)
        logger.debug('Checking if RS232 communication is available')
        try:
            self.get_version()
        except MotorError:
            raise
        logger.debug('TCP and RS232 both OK.')
        self.load_settings()
        self.emit('connect-equipment')
    def disconnect_from_controller(self):
        if not self.connected():
            raise MotorError('Not connected!')
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()
        del self.socket
        self.socket = None
        GObject.idle_add(lambda dummy: (self.emit('disconnect-equipment') and False), None)
    def do_communication(self, cmd):
        with self.comm_lock:
            if not self.connected():
                raise MotorError('Cannot communicate: socket not open.')
            readable, exceptional = select.select([self.socket], [], [self.socket], 0)[0:3:2]
            if exceptional:
                self.disconnect_from_controller()
                raise MotorError('Communication error.')
            while readable:
                res = self.socket.recv(9)
                if not res:
                    self.disconnect_from_controller()
                    raise MotorError('Socket closed.')
                readable = select.select([self.socket], [], [], 0)[0]
            if cmd is not None:
                writable, exceptional = select.select([], [self.socket], [self.socket], 0)[1:3]
                if not writable:
                    raise MotorError('Cannot write socket.')
                if exceptional:
                    self.disconnect_from_controller()
                    raise MotorError('Communication error.')
                chars_sent = 0
                while chars_sent < len(cmd):
                    chars_sent += self.socket.send(cmd[chars_sent:])
            readable, exceptional = select.select([self.socket], [], [self.socket], self.timeout)[0:3:2]
            if not readable:
                self.disconnect_from_controller()
                raise MotorError('Communication error. Controller may not be connected')
            result = ''
            while readable:
                result = result + self.socket.recv(9)
                if len(result) == 9:
                    break
                readable = select.select([self.socket], [], [], 1)[0]
            if result == '' and cmd is not None:
                self.disconnect_from_controller()
                raise MotorError('Communication error. Controller may not be connected')
            if len(result) != 9:
                raise MotorError('Invalid message received: *' + result + '*' + str(len(result)))
        return result
                
class StepperMotor(GObject.GObject):
    __gsignals__ = {'motor-start':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'motor-report':(GObject.SignalFlags.RUN_FIRST, None, (float, float, float)),
                    'motor-stop':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'motor-limit':(GObject.SignalFlags.RUN_FIRST, None, (bool, bool)),
                    'settings-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    }
    mot_idx = GObject.property(type=int, default=0, minimum=0, maximum=100)
    alias = GObject.property(type=str, default='<unknown motor>')
    name = GObject.property(type=str, default='<unknown motor>')
    step_to_cal = GObject.property(type=float, default=1 / 200.0)
    f_clk = GObject.property(type=int, default=16000000)
    softlimits = GObject.property(type=object)
    settings_timeout = 60
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
        self.driver().motors[self.name] = self
        self.limitdata = None
        for p in list(self.props):
            self.connect('notify::' + p.name, lambda mot, prop:self.emit('settings-changed'))
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
        GObject.idle_add(self.motor_monitor)
    def do_motor_stop(self):
        self.driver().save_settings()
    def motor_monitor(self):
        pos = self.get_pos()
        if (min(self.softlimits) > pos) or (max(self.softlimits) < pos):
            self.stop()
        speed = self.get_speed()
        self.emit('motor-report', pos, self.get_speed(), self.get_load())
        self.check_limits()
        if speed != 0:
            return True
        else:
            self.emit('motor-stop')
            return False
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
    def refresh_settings(self, paramname=None):
        print "Refreshing settings."
        params = [('Max_speed', 4), ('Max_accel', 5), ('Max_current', 6), ('Standby_current', 7),
                  ('Right_limit_disable', 12), ('Left_limit_disable', 13), ('Ustep_resol', 140),
                  ('Ramp_div', 153), ('Pulse_div', 154), ('Mixed_decay_threshold', 203),
                  ('Freewheeling_delay', 204), ('Stallguard_threshold', 205), ('Fullstep_threshold', 211)]
        if paramname is not None:
            params = [p for p in params if p[0] == paramname]
        changed = False
        for name, idx in params:
            newval = self.driver().execute(6, idx, self.mot_idx)
            if name not in self.settings or newval != self.settings[name]:
                self.settings[name] = newval
                changed = True
        self.settings['__timestamp__'] = time.time()
        self.emit('settings-changed') 
    def get_load(self):
        return self.driver().execute(6, 206, self.mot_idx)
    def get_accel(self, raw=False):
        val = self.driver().execute(6, 135, self.mot_idx)
        if raw:
            return val
        else:
            return self.conv_accel_phys(val)
    def get_left_limit(self):
        return bool(self.driver().execute(6, 11, self.mot_idx))
    def get_right_limit(self):
        return bool(self.driver().execute(6, 10, self.mot_idx))
    def get_target_reached(self):
        return bool(self.driver().execute(6, 8, self.mot_idx))
    def get_speed(self, raw=False):
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
        val = self.driver().execute(6, 0, self.mot_idx)
        if raw:
            return val
        else:
            return self.conv_pos_phys(val)
    def set_target_pos(self, pos, raw=False):
        if not raw:
            pos = self.conv_pos_raw(pos)
        return self.driver().execute(5, 0, self.mot_idx, pos)
    def get_pos(self, raw=False):
        val = self.driver().execute(6, 1, self.mot_idx)
        if raw:
            return val
        else:
            return self.conv_pos_phys(val)
    def set_pos(self, pos, raw=False):
        if not raw:
            pos = self.conv_pos_raw(pos)
        return self.driver().execute(5, 1, self.mot_idx, pos)
    def get_max_speed(self, raw=False):
        val = self.get_settings()['Max_speed']
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
        val = self.get_settings()['Max_accel']
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
        return (self.get_settings()['Max_current'] * 4.0) / 255
    def set_max_peak_current(self, Ipeak, make_default=False):
        self.driver().execute(5, 6, self.mot_idx, (Ipeak * 255) / 4.0)
        if make_default:
            self.driver().execute(7, 6, self.mot_idx)
        self.refresh_settings('Max_current')
    def get_max_raw_current(self):
        return (self.get_settings()['Max_current'])
    def set_max_raw_current(self, I, make_default=False):
        self.driver().execute(5, 6, self.mot_idx, I)
        if make_default:
            self.driver().execute(7, 6, self.mot_idx)
        self.refresh_settings('Max_current')
    def get_max_rms_current(self):
        return (self.get_settings()['Max_current'] * 2.8) / 255
    def set_max_rms_current(self, Irms, make_default=False):
        self.driver().execute(5, 6, self.mot_idx, (Irms * 255) / 2.8)
        if make_default:
            self.driver().execute(7, 6, self.mot_idx)
        self.refresh_settings('Max_current')
    def get_standby_peak_current(self):
        return (self.get_settings()['Standby_current'] * 4.0) / 255
    def set_standby_peak_current(self, Ipeak, make_default=False):
        self.driver().execute(5, 7, self.mot_idx, (Ipeak * 255) / 4)
        if make_default:
            self.driver().execute(7, 7, self.mot_idx)
        self.refresh_settings('Standby_current')
    def get_standby_raw_current(self):
        return (self.get_settings()['Standby_current'])
    def set_standby_raw_current(self, I, make_default=False):
        self.driver().execute(5, 7, self.mot_idx, I)
        if make_default:
            self.driver().execute(7, 7, self.mot_idx)
        self.refresh_settings('Standby_current')
    def get_standby_rms_current(self):
        return (self.get_settings()['Standby_current'] * 2.8) / 255
    def set_standby_rms_current(self, Irms, make_default=False):
        self.driver().execute(5, 7, self.mot_idx, (Irms * 255) / 2.8)
        if make_default:
            self.driver().execute(7, 7, self.mot_idx)
        self.refresh_settings('Standby_current')
    def get_right_limit_disable(self):
        return self.get_settings()['Right_limit_disable']
    def set_right_limit_disable(self, disabled, make_default=False):
        self.driver().execute(5, 12, self.mot_idx, disabled)
        if make_default:
            self.driver().execute(7, 12, self.mot_idx)
        self.refresh_settings('Right_limit_disable')
    def get_left_limit_disable(self):
        return self.get_settings()['Left_limit_disable']
    def set_left_limit_disable(self, disabled, make_default=False):
        self.driver().execute(5, 13, self.mot_idx, disabled)
        if make_default:
            self.driver().execute(7, 13, self.mot_idx)
        self.refresh_settings('Left_limit_disable')
    def get_ustep_resolution(self):
        return self.get_settings()['Ustep_resol']
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
        return self.get_settings()['Ramp_div']
    def set_ramp_div(self, ramp_div, make_default=False):
        self.driver().execute(5, 153, self.mot_idx, ramp_div)
        if make_default:
            self.driver().execute(7, 153, self.mot_idx)
        self.refresh_settings('Ramp_div')
    def get_pulse_div(self):
        return self.get_settings()['Pulse_div']
    def set_pulse_div(self, pulse_div, make_default=False):
        self.driver().execute(5, 154, self.mot_idx, pulse_div)
        if make_default:
            self.driver().execute(7, 154, self.mot_idx)
        self.refresh_settings('Pulse_div')
    def get_mixed_decay_threshold(self):
        return self.get_settings()['Mixed_decay_threshold']
    def set_mixed_decay_threshold(self, mdt, make_default=False):
        self.driver().execute(5, 203, self.mot_idx, mdt)
        if make_default:
            self.driver().execute(7, 203, self.mot_idx)
        self.refresh_settings('Mixed_decay_threshold')
    def get_freewheeling_delay(self):
        return self.get_settings()['Freewheeling_delay']
    def set_freewheeling_delay(self, fwd, make_default=False):
        self.driver().execute(5, 204, self.mot_idx, fwd)
        if make_default:
            self.driver().execute(7, 204, self.mot_idx)
        self.refresh_settings('Freewheeling_delay')
    def get_stallguard_threshold(self):
        return self.get_settings()['Stallguard_threshold']
    def set_stallguard_threshold(self, sgt, make_default=False):
        self.driver().execute(5, 205, self.mot_idx, sgt)
        if make_default:
            self.driver().execute(7, 205, self.mot_idx)
        self.refresh_settings('Stallguard_threshold')
    def get_fullstep_threshold(self):
        return self.get_settings()['Fullstep_threshold']
    def set_fullstep_threshold(self, fst, make_default=False):
        self.driver().execute(5, 211, self.mot_idx, fst)
        if make_default:
            self.driver().execute(7, 211, self.mot_idx)
        self.refresh_settings('Fullstep_threshold')
    def conv_speed_raw(self, speed_phys):
        settings = self.get_settings()
        return int(speed_phys * 2 ** settings['Pulse_div'] * 2048.0 * 32 * 2 ** settings['Ustep_resol'] / (self.step_to_cal * self.f_clk))
    def conv_speed_phys(self, speed_raw):
        settings = self.get_settings()
        return self.step_to_cal * speed_raw * self.f_clk / (2 ** settings['Pulse_div'] * 2048.0 * 32 * 2 ** settings['Ustep_resol'])
    def conv_pos_raw(self, pos_phys):
        settings = self.get_settings()
        return int(pos_phys / self.step_to_cal * 2 ** settings['Ustep_resol'])
    def conv_pos_phys(self, pos_raw):
        settings = self.get_settings()
        return pos_raw * self.step_to_cal / 2 ** settings['Ustep_resol']
    def conv_accel_raw(self, accel_phys):
        settings = self.get_settings()
        return int(accel_phys / (self.f_clk ** 2 * self.step_to_cal) * (2 ** (settings['Pulse_div'] + settings['Ramp_div'] + 29) * 2 ** settings['Ustep_resol'])) 
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
    def moveto(self, pos, raw=False, blocking=False):
        moving = self.driver().moving()
        if moving and self.name not in moving:
            raise MotorError('Another motor is currently moving.')
        if not raw:
            physpos = pos
            pos = self.conv_pos_raw(pos)
        else:
            physpos = self.conv_pos_phys(pos)
        if (min(self.softlimits) > physpos) or (physpos > max(self.softlimits)):
            raise MotorError('Target position outside software limits')
        self.emit('motor-start')
        self.driver().execute(4, 0, self.mot_idx, pos)
        if blocking:
            while self.is_moving():
                GObject.main_context_default().iteration(True)                
    def moverel(self, pos, raw=False, blocking=False):
        moving = self.driver().moving()
        if moving and self.name not in moving:
            raise MotorError('Another motor is currently moving.')
        if not raw:
            physpos = pos
            pos = self.conv_pos_raw(pos)
        else:
            physpos = self.conv_pos_phys(pos)
        physpos = self.get_pos(raw=False) + physpos
        if (min(self.softlimits) > physpos) or (physpos > max(self.softlimits)):
            raise MotorError('Target position outside software limits')
        self.emit('motor-start')
        self.driver().execute(4, 1, self.mot_idx, pos)
        if blocking:
            while self.is_moving():
                GObject.main_context_default().iteration(True)                
    def get_settings(self):
        if not self.settings or self.settings['__timestamp__'] < time.time() - self.settings_timeout:
            self.refresh_settings()
        return self.settings
    def calibrate_pos(self, pos=0, raw=False):
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
