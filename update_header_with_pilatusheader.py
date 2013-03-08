import sastool
import os

paramdir = '/home/labuser/credo_data/current/param'
cbfdir = '/net/pilatus300k.saxs/disk2/images'

for hn in os.listdir(paramdir):
    if not hn.endswith('.param'): continue
    try:
        h = sastool.classes.SASHeader(paramdir + '/' + hn)
    except IOError:
        print "Error loading: ", hn
    try:
        ph = sastool.io.twodim.readcbf(cbfdir + '/' + hn.replace('.param', '.cbf'), load_header=True, load_data=False)[0]
    except IOError:
        print "Error loading cbf for", hn
    h.update(ph)
    h.write(paramdir + '/' + hn)
    print hn, "done successfully."
    
