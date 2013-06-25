import sastool
import numpy as np
import os
import gc
import re
import ConfigParser
import logging
import functools
from gi.repository import GObject
import multiprocessing
from multiprocessing import Queue
import uuid

from .subsystem import SubSystem, SubSystemError
from ...utils import objwithgui

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ReductionTask(object):
    Reduce = 'reduce'
    Kill = 'kill'

class ExpSelector(object):
    """Select an exposure (using headers) which fulfills several criteria."""
    def __init__(self, headerformat='crd_%05d.param', datadirs=['.']):
        self.headerformat = headerformat
        self.datadirs = datadirs
        self._headercache = None
    def refresh_cache(self):
        if self._headercache is not None:
            del self._headercache
            gc.collect()
        regex = re.compile(sastool.misc.re_from_Cformatstring_numbers(self.headerformat)[:-1])
        headerfiles = []
        for d in self.datadirs:
            headerfiles.extend([os.path.join(d, f) for f in os.listdir(d) if regex.match(f) is not None])
        self._headercache = [sastool.classes.SASHeader(hf) for hf in headerfiles]
    def select(self, hdr_to_compare, equal=[], less=[], greater=[], func=[], sorting='Date', reversesort=False):
        """Select an exposure (using the headers) which fulfills several criteria.
        
        Inputs:
            hdr_to_compare: a header (or simply a dictionary) to which all headers will be compared
            equal: list of header attributes (such as 'Title', 'Dist' etc.) the values of which should be equal 
                to the corresponding ones in hdr_to_compare
            less: list of header attributes the values of which should be less than the corresponding ones in
                hdr_to_compare
            greater: list of header attributes the values of which should be greater than the corresponding ones
                in hdr_to_compare
            func: list of boolean functions. Each one will be called in turn with two arguments: hdr_to_compare and
                the current header to be tested. Returning True means the header is valid, False means invalid.
            sorting: the attribute name (or a key function of a similar call arguments as in func), by which the 
                valid headers will be sorted
            reversesort: if the sort order is to be reversed
        
        Output:
            the first header from the sorted, valid headers.
        """
        if self._headercache is None:
            self.refresh_cache()
        lis = self._headercache[:]
        for attr in equal:
            lis = [l for l in lis if (attr in l) and (l[attr] == hdr_to_compare[attr])]
        for attr in less:
            lis = [l for l in lis if (attr in l) and (l[attr] < hdr_to_compare[attr])]
        for attr in greater:
            lis = [l for l in lis if (attr in l) and (l[attr] > hdr_to_compare[attr])]
        for f in func:
            lis = [l for l in lis if f(hdr_to_compare, l)]
        if sorting is None:
            return lis
        if not callable(sorting):
            lis = [l for l in lis if sorting in l]
            lis.sort(key=lambda l:l[sorting], reverse=reversesort)
        elif callable(sorting):
            lis.sort(key=lambda l:sorting(hdr_to_compare, l), reverse=reversesort)
        return lis[0]

class DataReductionSettings(object):
    def __init__(self, dr):
        
        self.props = [{'name':p.name, 'default_value':p.default_value} for p in dr.props]
        self.vals = dr.__propvalues__
    def get_property(self, key):
        if key in self.vals:
            return self.vals[key]
        else:
            return [p for p in self.props if p['name'] == key][0]['default_value']

class ReductionWorker(multiprocessing.Process):
    def __init__(self, group, name, inqueue, outqueue):
        multiprocessing.Process.__init__(self, group=group, name=name)
        self.inqueue = inqueue
        self.outqueue = outqueue
        self.currentjob = None
    def run(self):
        while True:
            try:
                (tasktype, exposure, self.currentjob, self.settings) = self.inqueue.get()
                if tasktype == ReductionTask.Kill:
                    break
            except multiprocessing.queues.Empty:
                continue
            self.exposureselector = ExpSelector(self.settings['headerformat'], self.settings['datadirs'])
            logger.info('Data reduction of ' + str(exposure.header) + ' starting.')
            exposure = self.do_step1(exposure)
            exposure = self.do_step2(exposure)
            exposure = self.do_step3(exposure)
            self.sendmsg(exposure)
        return
    def sendmsg(self, msg):
        if isinstance(msg, basestring):
            logger.info(msg)
        self.outqueue.put((self.currentjob, msg))
    def do_step1(self, exposure):
        self.sendmsg('Reductions step #1 (scaling & geometry) on ' + str(exposure.header) + ' starting.')
        if self.settings['do-monitor']:
            moniattr = self.settings['monitor-attr']
            self.sendmsg('Normalizing intensities according to \'%s\'.' % moniattr)
            exposure = exposure / exposure[moniattr]
            exposure.header.add_history('Corrected for monitor: ' + moniattr)
        if self.settings['do-solidangle']:
            self.sendmsg('Doing solid angle correction.')
            exposure = exposure * sastool.utils2d.corrections.solidangle(exposure.tth, exposure['DistCalibrated'])
            exposure.header.add_history('Corrected for solid angle.')
        if self.settings['do-transmission']:
            self.sendmsg('Normalizing by transmission.')
            exposure = exposure / sastool.misc.errorvalue.ErrorValue(exposure['Transm'], exposure['TransmError'])
            exposure.header.add_history('Corrected for transmission')
            if self.settings['transmission-selfabsorption']:
                self.sendmsg('Angle-dependent self-absorption correction.')
                exposure *= sastool.utils2d.corrections.angledependentabsorption(exposure.tth, exposure['Transm'])
                exposure.header.add_history('Corrected for angle-dependent self-absorption.')
        self.sendmsg('Reduction step #1 (scaling & geometry) on ' + str(exposure.header) + ' done.')
        return exposure
    
    def do_step2(self, exposure):
        if self.settings['do-bgsub']:
            if exposure['Title'] == self.settings['bg-name']:
                self.sendmsg('Skipping background subtraction from background.')
                return exposure
            self.sendmsg('Reduction step #2 (background subtraction) on ' + str(exposure.header) + ' starting.')
            if self.settings['bg-select-method'] == 'nearest':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings['bg-name']
                bgheader = self.exposureselector.select(header, equal=['Title'],
                                     func=[lambda h0, h1: (abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings['bg-energy-tolerance']),
                                           lambda h0, h1: (abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings['bg-dist-tolerance'])],
                                     sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(self.settings['fileformat'] % bgheader['FSN'], dirs=self.exposureselector.datadirs)
            elif self.settings['bg-select-method'] == 'prev':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings['bg-name']
                bgheader = self.exposureselector.select(header, equal=['Title'], less=['Date'],
                                     func=[lambda h0, h1: (abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings['bg-energy-tolerance']),
                                           lambda h0, h1: (abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings['bg-dist-tolerance'])],
                                     sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(self.settings['fileformat'] % bgheader['FSN'], dirs=self.exposureselector.datadirs)
            elif self.settings['bg-select-method'] == 'next':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings['bg-name']
                bgheader = self.exposureselector.select(header, equal=['Title'], greater=['Date'],
                                     func=[lambda h0, h1: (abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings['bg-energy-tolerance']),
                                           lambda h0, h1: (abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings['bg-dist-tolerance'])],
                                     sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(self.settings['fileformat'] % bgheader['FSN'], dirs=self.exposureselector.datadirs)
            else:
                bg = sastool.classes.SASExposure(self.settings['bg-select-method'], dirs=self.exposureselector.datadirs)
            self.sendmsg('Found background: ' + str(bg.header))
            bg = self.do_step1(bg)
            exposure = exposure - bg
            exposure.header.add_history('Subtracted background: ' + str(bg.header))
            exposure.header['FSNempty'] = bg.header['FSN']
            self.sendmsg('Reduction step #2 (background subtraction) on ' + str(exposure.header) + ' done.')
        if self.settings['do-thickness']:
            self.sendmsg('Normalizing by thickness.')
            exposure /= exposure.header['Thickness']
            exposure.header.add_history('Normalized by thickness.')
        return exposure
    def do_step3(self, exposure):
        if exposure['Title'] == self.settings['bg-name']:
            self.sendmsg('Skipping absolute normalization of a background measurement.')
            return exposure
        if self.settings['do-absint']:
            self.sendmsg('Reduction step #3 (absolute intensity) on ' + str(exposure.header) + ' starting.')
            if self.settings['absint-select-method'] == 'nearest':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings['absint-name']
                refheader = self.exposureselector.select(header, equal=['Title'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings['absint-energy-tolerance'],
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings['absint-dist-tolerance']],
                                      sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(self.settings['fileformat'] % refheader['FSN'], dirs=self.exposureselector.datadirs)
            elif self.settings['absint-select-method'] == 'prev':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings['absint-name']
                refheader = self.exposureselector.select(header, equal=['Title'], less=['Date'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings['absint-energy-tolerance'],
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings['absint-dist-tolerance']],
                                      sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(self.settings['fileformat'] % refheader['FSN'], dirs=self.exposureselector.datadirs)
            elif self.settings['absint-select-method'] == 'next':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings['absint-name']
                refheader = self.exposureselector.select(header, equal=['Title'], greater=['Date'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings['absint-energy-tolerance'],
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings['absint-dist-tolerance']],
                                      sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(self.settings['fileformat'] % refheader['FSN'], dirs=self.exposureselector.datadirs)
            else:
                ref = sastool.classes.SASExposure(self.settings['absint-select-method'], dirs=self.exposureselector.datadirs)
            ref = self.do_step1(ref)
            ref = self.do_step2(ref)
            qmin = self.settings['absint-qmin']
            if qmin < 0:
                qmin = None
            qmax = self.settings['absint-qmax']
            if qmax < 0:
                qmax = None
            reffile = sastool.classes.SASCurve(self.settings['absint-reffile']).trim(qmin, qmax)
            self.sendmsg('Absolute intensity reference dataset loaded from %s; %g <= q <= %g; %d data points.' % (self.settings['absint-reffile'], reffile.q.min(), reffile.q.max(), len(reffile)))
            self.sendmsg('Reference measurement loaded: ' + str(ref.header))
            exposure.header.add_history('Absolute reference measurement: ' + str(ref.header))
            exposure.header.add_history('Absolute reference dataset: ' + self.settings['absint-reffile'])
            refq = ref.get_qrange()
            self.sendmsg('Default q-range for reference measurement: %g <= q <= %g; %d data points.' % (refq.min(), refq.max(), len(refq)))
            radref = ref.radial_average(reffile.q).sanitize(0, np.inf, 'Intensity')
            self.sendmsg('Radial averaged reference measurement: %g <= q <= %g; %d data points.' % (radref.q.min(), radref.q.max(), len(radref)))
            exposure.header.add_history('Absolute scaling interval: %g <= q <= %g; % data points.' % (radref.q.min(), radref.q.max(), len(radref)))
            scalefactor = radref.scalefactor(reffile)
            exposure.header.add_history('Absolute scaling factor: %s' % str(scalefactor))
            self.sendmsg('Absolute scaling factor:' + str(scalefactor))
            exposure = exposure * scalefactor
            self.sendmsg('Reduction step #3 (absolute intensity) on ' + str(exposure.header) + ' done.')
            exposure.header['FSNref1'] = ref.header['FSN']
            exposure.header['NormFactor'] = float(scalefactor)
            exposure.header['NormFactorRelativeError'] = scalefactor.err
            exposure.header['Thicknessref1'] = ref.header['Thickness']
        return exposure
    
class SubSystemDataReduction(SubSystem):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'message':(GObject.SignalFlags.RUN_FIRST, None, (long, str)),
                    'done':(GObject.SignalFlags.RUN_FIRST, None, (long, object)), }
    filebegin = GObject.property(type=str, nick='IO::File_begin', blurb='Filename prefix', default='crd')
    ndigits = GObject.property(type=int, nick='IO::Number_digits', blurb='Number of digits in FSN', default=5, minimum=1),
    do_bgsub = GObject.property(type=bool, nick='Background subtraction::Enabled', blurb='Do background subtraction?', default=True),
    do_absint = GObject.property(type=bool, nick='Absolute intensity::Enabled', blurb='Do absolute intensity scaling?', default=True)
    do_solidangle = GObject.property(type=bool, nick='Solid angle::Enabled', blurb='Do solid-angle correction?', default=True)
    do_transmission = GObject.property(type=bool, nick='Transmission::Enabled', blurb='Do transmission correction?', default=True)
    do_thickness = GObject.property(type=bool, nick='Scaling::Thickness', blurb='Scale by sample thickness?', default=True)
    do_monitor = GObject.property(type=bool, nick='Scaling::Monitor', blurb='Scale by monitor counts?', default=True)
    bg_select_method = GObject.property(type=str, nick='Background subtraction::Select_method', blurb='Background exposure selecting method', default='nearest')  # 'prev', 'next', 'nearest'. Otherwise it is treated as a filename. 
    bg_name = GObject.property(type=str, nick='Background subtraction::Name', blurb='Name of the background measurement', default='Empty beam')
    bg_dist_tolerance = GObject.property(type=float, nick='Background subtraction::Dist_tolerance_mm', blurb='Distance tolerance for background subtraction', minimum=0, maximum=1e6, default=20)  # mm
    bg_energy_tolerance = GObject.property(type=float, nick='Background subtraction::Energy_tolerance_eV', blurb='Energy tolerance for background subtraction', minimum=0, maximum=1e6, default=2)  # eV
    absint_select_method = GObject.property(type=str, nick='Absolute intensity::Select_method', blurb='Absolute intensity exposure selecting method', default='nearest')  # 'prev', 'next', 'nearest'. Otherwise it is treated as a filename. 
    absint_name = GObject.property(type=str, nick='Absolute intensity::Name', blurb='Name of the absolute reference measurement', default='Glassy Carbon')
    absint_dist_tolerance = GObject.property(type=float, nick='Absolute intensity::Dist_tolerance_mm', blurb='Distance tolerance for absolute intensity calibration', minimum=0, maximum=1e6, default=20)  # mm
    absint_energy_tolerance = GObject.property(type=float, nick='Absolute intensity::Energy_tolerance_eV', blurb='Energy tolerance for absolute intensity calibration', minimum=0, maximum=1e6, default=2)  # eV
    absint_reffile = GObject.property(type=str, nick='Absolute intensity::Ref_filename', blurb='Absolute intensity reference dataset filename', default='')
    monitor_attr = GObject.property(type=str, nick='Monitor::Header_attribute_name', blurb='Monitor header attribute name', default='MeasTime')
    transmission_selfabsorption = GObject.property(type=bool, nick='Transmission::Self_absorption_correction', blurb='Do self-absorption correction?', default=True)
    absint_qmin = GObject.property(type=float, nick='Absolute intensity::Q_min', blurb='Lower q-cutoff for absolute reference dataset', minimum= -1e6, maximum=1e6, default=0)
    absint_qmax = GObject.property(type=float, nick='Absolute intensity::Q_max', blurb='Upper q-cutoff for absolute reference dataset', minimum= -1e6, maximum=1e6, default=0)
    __propvalues__ = None
    _reduction_thread = None
    _inqueue = None
    def __init__(self, credo):
        self._OWG_nogui_props.append('configfile')
        self._OWG_hints['filebegin'] = {objwithgui.OWG_Hint_Type.OrderPriority:0}
        self._OWG_hints['ndigits'] = {objwithgui.OWG_Hint_Type.OrderPriority:1}
        self._OWG_hints['do-monitor'] = {objwithgui.OWG_Hint_Type.OrderPriority:2}
        self._OWG_hints['do-solidangle'] = {objwithgui.OWG_Hint_Type.OrderPriority:3}
        self._OWG_hints['do-transmission'] = {objwithgui.OWG_Hint_Type.OrderPriority:4}
        self._OWG_hints['transmission-selfabsorption'] = {objwithgui.OWG_Hint_Type.OrderPriority:5}
        self._OWG_hints['do-bgsub'] = {objwithgui.OWG_Hint_Type.OrderPriority:6}
        self._OWG_hints['do-thickness'] = {objwithgui.OWG_Hint_Type.OrderPriority:7}
        self._OWG_hints['do-absint'] = {objwithgui.OWG_Hint_Type.OrderPriority:8}

        self._OWG_hints['monitor_attr'] = {objwithgui.OWG_Hint_Type.OrderPriority:9}
        
        self._OWG_hints['bg-name'] = {objwithgui.OWG_Hint_Type.OrderPriority:10}
        self._OWG_entrytypes['bg-select-method'] = objwithgui.OWG_Param_Type.ListOfStrings
        self._OWG_hints['bg-select-method'] = {objwithgui.OWG_Hint_Type.ChoicesList:['nearest', 'prev', 'next'], objwithgui.OWG_Hint_Type.OrderPriority:11}
        self._OWG_hints['bg-dist-tolerance'] = {objwithgui.OWG_Hint_Type.OrderPriority:12}
        self._OWG_hints['bg-energy-tolerance'] = {objwithgui.OWG_Hint_Type.OrderPriority:13}

        self._OWG_hints['absint-name'] = {objwithgui.OWG_Hint_Type.OrderPriority:14}
        self._OWG_entrytypes['absint-select-method'] = objwithgui.OWG_Param_Type.ListOfStrings
        self._OWG_hints['absint-select-method'] = {objwithgui.OWG_Hint_Type.ChoicesList:['nearest', 'prev', 'next'], objwithgui.OWG_Hint_Type.OrderPriority:15}
        self._OWG_hints['absint-dist-tolerance'] = {objwithgui.OWG_Hint_Type.OrderPriority:16}
        self._OWG_hints['absint-energy-tolerance'] = {objwithgui.OWG_Hint_Type.OrderPriority:17}
        self._OWG_hints['absint-reffile'] = {objwithgui.OWG_Hint_Type.OrderPriority:18}
        self._OWG_entrytypes['absint-reffile'] = objwithgui.OWG_Param_Type.File
        self._OWG_hints['absint-qmin'] = {objwithgui.OWG_Hint_Type.OrderPriority:19}
        self._OWG_hints['absint-qmax'] = {objwithgui.OWG_Hint_Type.OrderPriority:20}
        
        SubSystem.__init__(self, credo)
        self._inqueue = multiprocessing.Queue()
        self._msgqueue = multiprocessing.Queue()
        self._reduction_thread = ReductionWorker(None, None, self._inqueue, self._msgqueue)
        self._reduction_thread.daemon = True
        self._reduction_thread.start()
        self._next_jobidx = 0L
        self._poller_sourceid = GObject.idle_add(self.poll_message_queue)
        # if self.datadirs is None:
        #    self.datadirs = ['.']
    def __del__(self):
        GObject.source_remove(self._poller_sourceid)
        self._kill_thread()
    def poll_message_queue(self):
        try:
            jobidx, msg = self._msgqueue.get_nowait()
        except multiprocessing.queues.Empty:
            return True
        if isinstance(msg, basestring):
            self.emit('message', jobidx, msg)
        else:
            self.emit('done', jobidx, msg)
        return True
    def start(self, exposure):
        self._next_jobidx += 1
        self._inqueue.put((ReductionTask.Reduce, exposure, self._next_jobidx, self.get_settings()))
        return self._next_jobidx
    def get_settings(self):
        dic = {p.name:self.get_property(p.name) for p in self.props}
        dic['headerformat'] = self.credo().subsystems['Files'].get_headerformat(self.filebegin, self.ndigits)
        dic['datadirs'] = self.credo().subsystems['Files'].exposureloadpath
        dic['fileformat'] = self.credo().subsystems['Files'].get_exposureformat(self.filebegin, self.ndigits)
        return dic
    def _kill_thread(self):
        while True:
            try:
                self._inqueue.get_nowait()
            except multiprocessing.queues.Empty:
                break
        self._inqueue.put((ReductionTask.Kill, None, None, None))
        self._reduction_thread.join()
