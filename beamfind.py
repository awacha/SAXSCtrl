import credo
import numpy as np
import sastool

mode = 'offline'

if mode == 'offline':
    fsns = [14, 15, 16]
    fsns = range(1, 14)
    datadirs = ('~/credo_data/current/param', '/net/pilatus300k/disk2/images')
elif mode == 'online':
    N = 10
    exptime = 0.3
    user = 'Wacha'
    title = 'Primary beam'

# long distance
pri = (236.85350144909282,
 251.17362887474806,
 313.36713105888782,
 302.90632875504036)
threshold = None

# short distance
# pri = (221, 239, 336, 349)
# threshold = None

# ---------------- do not edit below this line ----------------------

if mode == 'online':
    c = credo.Credo('genix', 'pilatus300k'); c.trim_detector()
    c.set_fileformat('beamtest')
    fsns = range(N)
    

pos = []
Imax = []
for i in fsns:
    if mode == 'online':
        ex = c.expose(exptime, title, user, plot=False);
    else:
        print i
        ex = sastool.SASExposure('beamtest_%05d.cbf', i, dirs=datadirs)
    # ex.header = sastool.SASHeader()
    pos.append(ex.find_beam_semitransparent(pri, threshold))
    Imax.append(ex.Intensity.max())
    
posx = [p[0] for p in pos]
posy = [p[1] for p in pos]

print 'Beam pos X   :', np.mean(posx), '+/-', np.std(posx)
print 'Beam pos Y   :', np.mean(posy), '+/-', np.std(posy)
print 'Max intensity:', np.mean(Imax), '+/-', np.std(Imax)
# c.pilatus.disconnect()
# del c
