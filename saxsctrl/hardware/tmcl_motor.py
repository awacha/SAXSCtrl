import serial
import logging

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
    def send_and_recv(self, instruction, type_=0, mot_bank=0, value=0):
        val_as_list = ()
        for i in range(4):
            val_as_list = ((value / (256 ** i)) % (256 ** (i + 1)),) + val_as_list
        cmd = (1, instruction, type_, mot_bank) + val_as_list
        cmd = cmd + (sum(cmd) % 256,)
        print "Command datagram ready"
        logger.debug('About to send TMCL command: ' + ''.join(hex(x) for x in cmd))
        cmd = ''.join(chr(x) for x in cmd)
        print "Sending datagram"
        self.rs232.write(cmd)
        print "Sent."
        result = self.rs232.read(9)
        print "Received."
        logger.debug('Got TMCL result: ' + ''.join(hex(ord(x)) for x in result))
        # validate checksum
        print "Validating checksum"
        if not (sum(ord(x) for x in result[:-1]) % 256 == ord(result[-1])):
            raise MotorError('Checksum error on received data!')
        print "Checking reply instruction"
        if not ord(result[3]) == instruction:
            raise MotorError('Invalid reply from TMCM module: not the same instruction.')
        print "Checking status"
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
        print "Converting value"
        value = sum([ord(result[4 + i]) * 256 ** (3 - i) for i in range(4)])
        print "Returning"
        return status, value
    def get_version(self):
        stat, ver = self.send_and_recv(136, 1)
        if ver / 0x10000 != 0x015f:
            raise MotorError('Invalid version signature: ' + hex(ver / 0x10000))
        ver = ver % 0x10000
        major = ver / 0x100
        minor = ver % 0x100
        return major, minor
    
        
class StepperMotor(object):
    def __init__(self, driver, mot_idx,name=None,alias=None):
        self.driver=driver
        if name is None:
            name='MOT_'+str(mot_idx+1)
        if alias is None:
            alias = name
        self.name=name
        self.alias=alias
    def get_raw_speed(self):
        pass
    def rot_left(self,speed):
        
            