#!/usr/bin/env python
import sastool
import os
import matplotlib.pyplot as plt

inputfolder = '/net/pilatus300k.saxs/disk2/images'
outputfolder = '/home/labuser/credo_data/current/png'

for f in os.listdir(inputfolder):
    if not f.endswith('.cbf') and not f.endswith('.tif'):
        continue
    try:
        ex = sastool.classes.SASExposure(f, noheader=True, dirs=[inputfolder])
    except IOError as ioe:
        print "ERROR: ", f, str(ioe)
        continue
    ex.plot2d(qrange_on_axis=False)
    plt.title(f)
    plt.savefig(os.path.join(outputfolder, 'lin_' + f + '.png'))
    plt.clf()
    ex.plot2d(zscale='log', qrange_on_axis=False)
    plt.title(f)
    plt.savefig(os.path.join(outputfolder, 'log_' + f + '.png'))
    plt.clf()
    del ex
    print f
    
