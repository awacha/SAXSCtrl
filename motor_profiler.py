import saxsctrl
import time
import datetime
import numpy as np

mc = saxsctrl.hardware.tmcl_motor.TMCM351('/dev/ttyUSB0')

# mot = saxsctrl.hardware.tmcl_motor.StepperMotor(mc, 0, alias='Sample_Y', positionfolder=None)
mot = saxsctrl.hardware.tmcl_motor.StepperMotor(mc, 1, alias='Sample_X', positionfolder=None)

mot.rot_left(1000)

while mot.is_moving():
    pass

speed_start = 10
speed_end = 2047
# Nspeed = speed_end - speed_start + 1
Nspeed = 500
nsample = 20

data = np.zeros((Nspeed, 3))
velocity = data[:, 0] = np.linspace(speed_start, speed_end, Nspeed)
samples = np.zeros(nsample)

def rewind_if_needed(veloc=1000):
    if veloc < 1000:
        veloc = 1000
    if mot.get_right_limit():
        print "Rewinding!"
        mot.rot_left(veloc)
        while mot.is_moving():
            pass

for i in range(Nspeed):
    rewind_if_needed(data[i, 0])
    mot.rot_right(data[i, 0])
    for n in range(nsample):
        samples[n] = mot.get_load()
        rewind_if_needed(data[i, 0])
    data[i, 1] = np.mean(samples)
    data[i, 2] = np.std(samples)
    print data[i, 0], data[i, 1], data[i, 2], i, '/', Nspeed

np.savetxt('loadprofile_right_' + str(datetime.datetime.now()) + '.txt', data)

