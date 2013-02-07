import matplotlib.pyplot as plt
import numpy as np

logfile = 'genixlog.txt'

starttime = 0

time = []
ht = []
curr = []
bits = []
asctime = []

with open(logfile, 'rt') as f:
    for l in f:
        at, t, data = l.split('|')
        t = float(t)
        if t < starttime:
            continue
        asctime.append(at)
        time.append(t)
        htstring, currstring, bitstring = data.split(',')
        ht.append(float(htstring.split("=")[1].split(' ')[0]))
        curr.append(float(currstring.split('=')[1].split(' ')[0]))
        bits.append(bitstring.split('=')[1])
        
time = [t - time[0] for t in time]

plt.close('all')
handles = []
handles.extend(plt.plot(time, ht, 'b.-', label='HT (kV)'))
plt.xlabel('Time (sec)')
plt.ylabel('High tension (kV)')
plt.axis(ymin=0, ymax=50)
plt.twinx()
handles.extend(plt.plot(time, curr, 'r.-', label='Curr (mA)'))
plt.ylabel('Current (mA)')
plt.axis(ymin=0, ymax=1)
plt.legend(handles, [h.get_label() for h in handles], loc='upper left', numpoints=1)
plt.title('GeniX operation archive')
plt.figtext(1, 0, 'genixlog ' + asctime[0], ha='right', va='bottom')
plt.show()            
