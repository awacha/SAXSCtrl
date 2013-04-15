import serial
import logging
import time
import struct
import multiprocessing
import threading
import os

# logger = logging.getLogger(__name__)
logger = logging.root
logger.setLevel(logging.DEBUG)

class MotorError(StandardError):
    pass

class TMCM351(object):
    def __init__(self, serial_device):
        self.rs232 = serial.Serial(serial_device)
        if not self.rs232.isOpen():
            raise MotorError('Cannot open RS-232 port ' + str(serial_device))
        self.rs232.timeout = 1
        self.rs232_lock = multiprocessing.Lock()
    def send_and_recv(self, instruction, type_=0, mot_bank=0, value=0):
        cmd = (1, instruction, type_, mot_bank) + struct.unpack('4B', struct.pack('>i', int(value)))
        cmd = cmd + (sum(cmd) % 256,)
        logger.debug('About to send TMCL command: ' + ''.join(hex(x) for x in cmd))
        cmd = ''.join(chr(x) for x in cmd)
        with self.rs232_lock:
            self.rs232.flushInput()
            self.rs232.write(cmd)
            result = self.rs232.read(9)
        if not result:
            raise MotorError('Communication error. Controller may not be connected')
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
        
class StepperMotor(object):
    settings_timeout = 60
    def __init__(self, driver, mot_idx, step_to_cal=1 / 200.0, name=None, alias=None, f_clk=16000000, positionfolder=None, possaveinterval=10):
        self.driver = driver
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
        self.posfilename = None
        self._kill_possaver = threading.Event()
        self.possaver = None
        if positionfolder is not None:
            self.posfilename = os.path.join(positionfolder, self.name + '.pos')
            try:
                self.load_pos()
            except IOError:
                pass
            self.possaver = threading.Thread(target=self._possaver_thread, args=(possaveinterval,))
            self.possaver.daemon = True
            self.possaver.start()
    def _possaver_thread(self, interval):
        while not self._kill_possaver.is_set():
            self._kill_possaver.wait(interval)
            self.save_pos()
        return
    def __del__(self):
        if self.possaver is not None:
            self._kill_possaver.set()
            self.possaver.join()
            self.possaver = None
    def save_pos(self):
        if self.posfilename is not None:
            with open(self.posfilename, 'w') as f:
                f.write(str(self.get_pos()))
    def load_pos(self):
        if self.posfilename is not None:
            with open(self.posfilename, 'r') as f:
                self.set_pos(int(f.read()))
    def refresh_settings(self):
        self.settings['Max_speed'] = self.driver.execute(6, 4, self.mot_idx)
        self.settings['Max_accel'] = self.driver.execute(6, 5, self.mot_idx)
        self.settings['Max_current'] = self.driver.execute(6, 6, self.mot_idx)
        self.settings['Standby_current'] = self.driver.execute(6, 7, self.mot_idx)
        self.settings['Right_limit_disable'] = self.driver.execute(6, 12, self.mot_idx)
        self.settings['Left_limit_disable'] = self.driver.execute(6, 13, self.mot_idx)
        self.settings['Ustep_resol'] = self.driver.execute(6, 140, self.mot_idx)
        self.settings['Ramp_div'] = self.driver.execute(6, 153, self.mot_idx)
        self.settings['Pulse_div'] = self.driver.execute(6, 154, self.mot_idx)
        self.settings['Mixed_decay_threshold'] = self.driver.execute(6, 203, self.mot_idx)
        self.settings['Freewheeling_delay'] = self.driver.execute(6, 204, self.mot_idx)
        self.settings['Stallguard_threshold'] = self.driver.execute(6, 205, self.mot_idx)
        self.settings['Fullstep_threshold'] = self.driver.execute(6, 211, self.mot_idx)
        self.settings['__timestamp__'] = time.time()
    def get_load(self):
        return self.driver.execute(6, 206, self.mot_idx)
    def get_accel(self):
        return self.driver.execute(6, 135, self.mot_idx)
    def get_left_limit(self):
        return bool(self.driver.execute(6, 11, self.mot_idx))
    def get_right_limit(self):
        return bool(self.driver.execute(6, 10, self.mot_idx))
    def get_target_reached(self):
        return bool(self.driver.execute(6, 8, self.mot_idx))
    def get_speed(self):
        return self.driver.execute(6, 3, self.mot_idx)
    def is_moving(self):
        return self.get_speed() != 0
    def get_target_pos(self):
        return self.driver.execute(6, 0, self.mot_idx)
    def set_target_pos(self, pos):
        return self.driver.execute(5, 0, self.mot_idx, pos)
    def get_pos_reached(self):
        return self.driver.execute(6, 8, self.mot_idx)
    def get_pos(self):
        return self.driver.execute(6, 1, self.mot_idx)
    def set_pos(self, pos):
        self.set_target_pos(pos)
        return self.driver.execute(5, 1, self.mot_idx, pos)
    def get_max_speed(self):
        return self.get_settings()['Max_speed']
    def set_max_speed(self, maxspeed, make_default=False):
        self.driver.execute(5, 4, self.mot_idx, maxspeed)
        if make_default:
            self.driver.execute(7, 4, self.mot_idx)
    def get_max_accel(self):
        return self.get_settings()['Max_accel']
    def set_max_accel(self, maxaccel, make_default=False):
        self.driver.execute(5, 5, self.mot_idx, maxaccel)
        if make_default:
            self.driver.execute(7, 5, self.mot_idx)
    def get_max_peak_current(self):
        return (self.get_settings()['Max_current'] * 4) / 255
    def set_max_peak_current(self, Ipeak, make_default=False):
        self.driver.execute(5, 6, self.mot_idx, (Ipeak * 255) / 4)
        if make_default:
            self.driver.execute(7, 6, self.mot_idx)
    def get_max_rms_current(self):
        return (self.get_settings()['Max_current'] * 2.8) / 255
    def set_max_rms_current(self, Irms, make_default=False):
        self.driver.execute(5, 6, self.mot_idx, (Irms * 255) / 2.8)
        if make_default:
            self.driver.execute(7, 6, self.mot_idx)
    def get_standby_peak_current(self):
        return (self.get_settings()['Standby_current'] * 4) / 255
    def set_standby_peak_current(self, Ipeak, make_default=False):
        self.driver.execute(5, 7, self.mot_idx, (Ipeak * 255) / 4)
        if make_default:
            self.driver.execute(7, 7, self.mot_idx)
    def get_standby_rms_current(self):
        return (self.get_settings()['Standby_current'] * 2.8) / 255
    def set_standby_rms_current(self, Irms, make_default=False):
        self.driver.execute(5, 7, self.mot_idx, (Irms * 255) / 2.8)
        if make_default:
            self.driver.execute(7, 7, self.mot_idx)
    def get_right_limit_disable(self):
        return self.get_settings()['Right_limit_disable']
    def set_right_limit_disable(self, disabled, make_default=False):
        self.driver.execute(5, 12, self.mot_idx, disabled)
        if make_default:
            self.driver.execute(7, 12, self.mot_idx)
    def get_left_limit_disable(self):
        return self.get_settings()['Left_limit_disable']
    def set_left_limit_disable(self, disabled, make_default=False):
        self.driver.execute(5, 13, self.mot_idx, disabled)
        if make_default:
            self.driver.execute(7, 13, self.mot_idx)
    def get_ustep_resolution(self):
        return self.get_settings()['Ustep_resol']
    def set_ustep_resolution(self, usrs, make_default=False):
        """Set microstep resolution.
        
        The number of microsteps is 2**usrs.
        
        usrs can be 0 to 6 (inclusive).
        """
        self.driver.execute(5, 140, self.mot_idx, usrs)
        if make_default:
            self.driver.execute(7, 140, self.mot_idx)
    def get_ramp_div(self):
        return self.get_settings()['Ramp_div']
    def set_ramp_div(self, ramp_div, make_default=False):
        self.driver.execute(5, 153, self.mot_idx, ramp_div)
        if make_default:
            self.driver.execute(7, 153, self.mot_idx)
    def get_pulse_div(self):
        return self.get_settings()['Pulse_div']
    def set_pulse_div(self, pulse_div, make_default=False):
        self.driver.execute(5, 154, self.mot_idx, pulse_div)
        if make_default:
            self.driver.execute(7, 154, self.mot_idx)
    def get_mixed_decay_threshold(self):
        return self.get_settings()['Mixed_decay_threshold']
    def set_mixed_decay_threshold(self, mdt, make_default=False):
        self.driver.execute(5, 203, self.mot_idx, mdt)
        if make_default:
            self.driver.execute(7, 203, self.mot_idx)
    def get_freewheeling_delay(self):
        return self.get_settings()['Freewheeling_delay']
    def set_freewheeling_delay(self, fwd, make_default=False):
        self.driver.execute(5, 204, self.mot_idx, fwd)
        if make_default:
            self.driver.execute(7, 204, self.mot_idx)
    def get_stallguard_threshold(self):
        return self.get_settings()['Stallguard_threshold']
    def set_stallguard_threshold(self, sgt, make_default=False):
        self.driver.execute(5, 205, self.mot_idx, sgt)
        if make_default:
            self.driver.execute(7, 205, self.mot_idx)
    def get_fullstep_threshold(self):
        return self.get_settings()['Fullstep_threshold']
    def set_fullstep_threshold(self, fst, make_default=False):
        self.driver.execute(5, 211, self.mot_idx, fst)
        if make_default:
            self.driver.execute(7, 211, self.mot_idx)
    def conv_speed_raw(self, speed_phys):
        settings = self.get_settings()
        return speed_phys * 2 ** settings['Pulse_div'] * 2048.0 * 32 * 2 ** settings['Ustep_resol'] / (self.step_to_cal * self.f_clk)
    def conv_speed_phys(self, speed_raw):
        settings = self.get_settings()
        return self.step_to_cal * speed_raw * self.f_clk / (2 ** settings['Pulse_div'] * 2048.0 * 32 * 2 ** settings['Ustep_resol'])
    def conv_pos_raw(self, pos_phys):
        settings = self.get_settings()
        return pos_phys / self.step_to_cal * 2 ** settings['Ustep_resol']
    def conv_pos_phys(self, pos_raw):
        settings = self.get_settings()
        return pos_raw * self.step_to_cal / 2 ** settings['Ustep_resol']
    def conv_accel_raw(self, accel_phys):
        settings = self.get_settings()
        return accel_phys / (self.f_clk ** 2 * self.step_to_cal) * (2 ** (settings['Pulse_div'] + settings['Ramp_div'] + 29) * 2 ** settings['Ustep_resol']) 
    def conv_accel_phys(self, accel_raw):
        settings = self.get_settings()
        return self.f_clk ** 2 * accel_raw / (2 ** (settings['Pulse_div'] + settings['Ramp_div'] + 29)) * (self.step_to_cal / 2 ** settings['Ustep_resol']) 
    def rot_left(self, speed):
        self.driver.execute(2, 0, self.mot_idx, speed)
    def rot_right(self, speed):
        self.driver.execute(1, 0, self.mot_idx, speed)
    def stop(self):
        self.driver.execute(3, 0, self.mot_idx, 0)
    def moveto(self, pos, relative=True):
        self.driver.execute(4, int(relative), self.mot_idx, pos)
    def get_settings(self):
        if not self.settings or self.settings['__timestamp__'] < time.time() - self.settings_timeout:
            self.refresh_settings()
        return self.settings
