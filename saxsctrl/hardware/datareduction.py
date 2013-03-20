import sastool
import numpy as np
import os
import gc
import re
import ConfigParser
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
import functools
from gi.repository import GObject
import multiprocessing
from multiprocessing import Queue
import uuid

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
    def __init__(self, group, name, killswitch, inqueue, outqueue):
        multiprocessing.Process.__init__(self, group=group, name=name)
        self.killswitch = killswitch
        self.inqueue = inqueue
        self.outqueue = outqueue
        self.currentjob = None
    def run(self):
        while not self.killswitch.is_set():
            try:
                (exposure, self.currentjob, self.settings) = self.inqueue.get(block=True, timeout=1)
            except multiprocessing.queues.Empty:
                continue
            self.exposureselector = ExpSelector(self.settings.get_property('headerformat'), self.settings.get_property('datadirs'))
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
        if self.settings.get_property('do-monitor'):
            self.sendmsg('Normalizing intensities according to \'%s\'.' % self.settings.get_property('monitor-attr'))
            exposure = exposure / exposure[self.settings.get_property('monitor-attr')]
            exposure.header.add_history('Corrected for monitor: ' + self.settings.get_property('monitor-attr'))
        if self.settings.get_property('do-solidangle'):
            self.sendmsg('Doing solid angle correction.')
            exposure = exposure * sastool.utils2d.corrections.solidangle(exposure.tth, exposure['DistCalibrated'])
            exposure.header.add_history('Corrected for solid angle.')
        if self.settings.get_property('do-transmission'):
            self.sendmsg('Normalizing by transmission.')
            exposure = exposure / sastool.misc.errorvalue.ErrorValue(exposure['Transm'], exposure['TransmError'])
            exposure.header.add_history('Corrected for transmission')
            if self.settings.get_property('transmission-selfabsorption'):
                self.sendmsg('Self-absorption correction.')
                exposure *= sastool.utils2d.corrections.angledependentabsorption(exposure.tth, exposure['Transm'])
                exposure.header.add_history('Corrected for angle-dependent self-absorption.')
        self.sendmsg('Reduction step #1 (scaling & geometry) on ' + str(exposure.header) + ' done.')
        return exposure
    def do_step2(self, exposure):
        if self.settings.get_property('do-bgsub'):
            if exposure['Title'] == self.settings.get_property('bg-name'):
                self.sendmsg('Skipping background subtraction from background.')
                return exposure
            self.sendmsg('Reduction step #2 (background subtraction) on ' + str(exposure.header) + ' starting.')
            if self.settings.get_property('bg-select-method') == 'nearest':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings.get_property('bg-name')
                bgheader = self.exposureselector.select(header, equal=['Title'],
                                     func=[lambda h0, h1: (abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings.get_property('bg-energy-tolerance')),
                                           lambda h0, h1: (abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings.get_property('bg-dist-tolerance'))],
                                     sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(self.settings.get_property('fileformat') % bgheader['FSN'], dirs=self.exposureselector.datadirs)
            elif self.settings.get_property('bg-select-method') == 'prev':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings.get_property('bg-name')
                bgheader = self.exposureselector.select(header, equal=['Title'], less=['Date'],
                                     func=[lambda h0, h1: (abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings.get_property('bg-energy-tolerance')),
                                           lambda h0, h1: (abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings.get_property('bg-dist-tolerance'))],
                                     sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(self.settings.get_property('fileformat') % bgheader['FSN'], dirs=self.exposureselector.datadirs)
            elif self.settings.get_property('bg-select-method') == 'next':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings.get_property('bg-name')
                bgheader = self.exposureselector.select(header, equal=['Title'], greater=['Date'],
                                     func=[lambda h0, h1: (abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings.get_property('bg-energy-tolerance')),
                                           lambda h0, h1: (abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings.get_property('bg-dist-tolerance'))],
                                     sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(self.settings.get_property('fileformat') % bgheader['FSN'], dirs=self.exposureselector.datadirs)
            else:
                bg = sastool.classes.SASExposure(self.settings.get_property('bg-select-method'), dirs=self.exposureselector.datadirs)
            self.sendmsg('Found background: ' + str(bg.header))
            bg = self.do_step1(bg)
            exposure = exposure - bg
            exposure.header.add_history('Subtracted background: ' + str(bg.header))
            exposure.header['FSNempty'] = bg.header['FSN']
            self.sendmsg('Reduction step #2 (background subtraction) on ' + str(exposure.header) + ' done.')
        if self.settings.get_property('do-thickness'):
            self.sendmsg('Normalizing by thickness.')
            exposure /= exposure.header['Thickness']
            exposure.header.add_history('Normalized by thickness.')
        return exposure
    def do_step3(self, exposure):
        if exposure['Title'] == self.settings.get_property('bg-name'):
            self.sendmsg('Skipping absolute normalization of a background measurement.')
            return exposure
        if self.settings.get_property('do-absint'):
            self.sendmsg('Reduction step #3 (absolute intensity) on ' + str(exposure.header) + ' starting.')
            if self.settings.get_property('absint-select-method') == 'nearest':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings.get_property('absint-name')
                refheader = self.exposureselector.select(header, equal=['Title'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings.get_property('absint-energy-tolerance'),
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings.get_property('absint-dist-tolerance')],
                                      sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(self.settings.get_property('fileformat') % refheader['FSN'], dirs=self.exposureselector.datadirs)
            elif self.settings.get_property('absint-select-method') == 'prev':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings.get_property('absint-name')
                refheader = self.exposureselector.select(header, equal=['Title'], less=['Date'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings.get_property('absint-energy-tolerance'),
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings.get_property('absint-dist-tolerance')],
                                      sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(self.settings.get_property('fileformat') % refheader['FSN'], dirs=self.exposureselector.datadirs)
            elif self.settings.get_property('absint-select-method') == 'next':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.settings.get_property('absint-name')
                refheader = self.exposureselector.select(header, equal=['Title'], greater=['Date'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.settings.get_property('absint-energy-tolerance'),
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.settings.get_property('absint-dist-tolerance')],
                                      sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(self.settings.get_property('fileformat') % refheader['FSN'], dirs=self.exposureselector.datadirs)
            else:
                ref = sastool.classes.SASExposure(self.settings.get_property('absint-select-method'), dirs=self.exposureselector.datadirs)
            ref = self.do_step1(ref)
            ref = self.do_step2(ref)
            qmin = self.settings.get_property('absint-qmin')
            if qmin < 0:
                qmin = None
            qmax = self.settings.get_property('absint-qmax')
            if qmax < 0:
                qmax = None
            reffile = sastool.classes.SASCurve(self.settings.get_property('absint-reffile')).trim(qmin, qmax)
            self.sendmsg('Absolute intensity reference dataset loaded from %s; %g <= q <= %g; %d data points.' % (self.settings.get_property('absint-reffile'), reffile.q.min(), reffile.q.max(), len(reffile)))
            self.sendmsg('Reference measurement loaded: ' + str(ref.header))
            exposure.header.add_history('Absolute reference measurement: ' + str(ref.header))
            exposure.header.add_history('Absolute reference dataset: ' + self.settings.get_property('absint-reffile'))
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
    
class DataReduction(GObject.GObject):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'message':(GObject.SignalFlags.RUN_FIRST, None, (long, str)),
                    'done':(GObject.SignalFlags.RUN_FIRST, None, (long, object)), }
    __gproperties__ = {'fileformat' :(str, 'IO::File_format', '2d file format string including extension', 'crd_%05d.cbf', GObject.PARAM_READWRITE),
                       'headerformat':(str, 'IO::Header_format', 'header file format string including extension', 'crd_%05d.param', GObject.PARAM_READWRITE),
                       'datadirs': (object, 'IO::Dir*', 'search path for data to be loaded', GObject.PARAM_READWRITE),
                       'do-bgsub': (bool, 'Background subtraction::Enabled', 'Do background subtraction?', True, GObject.PARAM_READWRITE),
                       'do-absint': (bool, 'Absolute intensity::Enabled', 'Do absolute intensity scaling?', True, GObject.PARAM_READWRITE),
                       'do-solidangle': (bool, 'Solid angle::Enabled', 'Do solid-angle correction?', True, GObject.PARAM_READWRITE),
                       'do-transmission' : (bool, 'Transmission::Enabled', 'Do transmission correction?', True, GObject.PARAM_READWRITE),
                       'do-thickness': (bool, 'Scaling::Thickness', 'Scale by sample thickness?', True, GObject.PARAM_READWRITE),
                       'do-monitor': (bool, 'Scaling::Monitor', 'Scale by monitor counts?', True, GObject.PARAM_READWRITE),
                       'bg-select-method':(str, 'Background subtraction::Select_method', 'Background exposure selecting method', 'nearest', GObject.PARAM_READWRITE),  # 'prev', 'next', 'nearest'. Otherwise it is treated as a filename. 
                       'bg-name' : (str, 'Background subtraction::Name', 'Name of the background measurement', 'Empty beam', GObject.PARAM_READWRITE),
                       'bg-dist-tolerance' : (float, 'Background subtraction::Dist_tolerance_mm', 'Distance tolerance for background subtraction', 0, 1e6, 20, GObject.PARAM_READWRITE),  # mm
                       'bg-energy-tolerance' : (float, 'Background subtraction::Energy_tolerance_eV', 'Energy tolerance for background subtraction', 0, 1e6, 2, GObject.PARAM_READWRITE),  # eV
                       'absint-select-method':(str, 'Absolute intensity::Select_method', 'Absolute intensity exposure selecting method', 'nearest', GObject.PARAM_READWRITE),  # 'prev', 'next', 'nearest'. Otherwise it is treated as a filename. 
                       'absint-name' : (str, 'Absolute intensity::Name', 'Name of the absolute reference measurement', 'Glassy Carbon', GObject.PARAM_READWRITE),
                       'absint-dist-tolerance' : (float, 'Absolute intensity::Dist_tolerance_mm', 'Distance tolerance for absolute intensity calibration', 0, 1e6, 20, GObject.PARAM_READWRITE),  # mm
                       'absint-energy-tolerance' : (float, 'Absolute intensity::Energy_tolerance_eV', 'Energy tolerance for absolute intensity calibration', 0, 1e6, 2, GObject.PARAM_READWRITE),  # eV
                       'absint-reffile':(str, 'Absolute intensity::Ref_filename', 'Absolute intensity reference dataset filename', '', GObject.PARAM_READWRITE),
                       'monitor-attr':(str, 'Monitor::Header_attribute_name', 'Monitor header attribute name', 'MeasTime', GObject.PARAM_READWRITE),
                       'transmission-selfabsorption':(bool, 'Transmission::Self_absorption_correction', 'Do self-absorption correction?', True, GObject.PARAM_READWRITE),
                       'absint-qmin':(float, 'Absolute intensity::Q_min', 'Lower q-cutoff for absolute reference dataset', -1e6, 1e6, 0, GObject.PARAM_READWRITE),
                       'absint-qmax':(float, 'Absolute intensity::Q_max', 'Upper q-cutoff for absolute reference dataset', -1e6, 1e6, 0, GObject.PARAM_READWRITE),
                      }
    __propvalues__ = None
    _reduction_thread = None
    _inqueue = None
    _kill_reduction_thread = None
    def do_get_property(self, prop):
        if prop.name not in self.__propvalues__:
            self.__propvalues__[prop.name] = prop.default_value
        return self.__propvalues__[prop.name]
    def do_set_property(self, prop, value):
        if prop.value_type.name in ['gdouble', 'gint']:
            if value < prop.minimum or value > prop.maximum:
                raise ValueError('Value for property %s is outside the limits.' % prop.name)
        self.__propvalues__[prop.name] = value
    def __init__(self, *args, **kwargs):
        GObject.GObject.__init__(self)
        self._inqueue = multiprocessing.Queue()
        self._kill_reduction_thread = multiprocessing.Event()
        self._msgqueue = multiprocessing.Queue()
        self._reduction_thread = ReductionWorker(None, None, self._kill_reduction_thread, self._inqueue, self._msgqueue)
        self._reduction_thread.daemon = True
        self._reduction_thread.start()
        self._next_jobidx = 0L
        if args and isinstance(args[0], DataReduction):
            self.__propvalues__ = args[0].__propvalues__.copy()
        else:
            self.__propvalues__ = {}
        for k in kwargs:
            self.set_property(k, kwargs[k])
        self._poller_sourceid = GObject.idle_add(self.poll_message_queue)
        # if self.datadirs is None:
        #    self.datadirs = ['.']
    def __del__(self):
        GObject.source_remove(self._poller_sourceid)
        self._kill_reduction_thread.set()
        self._kill_reduction_thread.join()
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
    def load_state(self, cfg=os.path.expanduser('~/.config/credo/dataredrc'), keep=[]):
        cp = ConfigParser.ConfigParser()
        cp.read(cfg)
        for prop in self.props:
            sec, opt = prop.nick.split('::')
            if prop.name in keep:
                continue
            if opt.endswith('*'):
                self.set_property(prop.name, [v for (n, v) in cp.items(sec) if n.startswith(opt[:-1])])
                continue
            if not cp.has_option(sec, opt):
                continue
            if prop.value_type.name == 'gchararray':
                self.set_property(prop.name, cp.get(sec, opt))
            elif prop.value_type.name == 'gint':
                self.set_property(prop.name, cp.getint(sec, opt))
            elif prop.value_type.name == 'gdouble':
                self.set_property(prop.name, cp.getfloat(sec, opt))
            elif prop.value_type.name == 'gboolean':
                self.set_property(prop.name, cp.getboolean(sec, opt))
            else:
                self.set_property(prop.name, cp.get(sec, opt))
        self.emit('changed')
    def save_state(self, cfg=os.path.expanduser('~/.config/credo/dataredrc')):
        cp = ConfigParser.ConfigParser()
        for prop in self.props:
            sec, opt = prop.nick.split('::')
            if not cp.has_section(sec):
                cp.add_section(sec)
            if opt.endswith('*'):
                lis = self.get_property(prop.name)
                for i, el in enumerate(lis):
                    cp.set(sec, opt[:-1] + '%05d' % i, el)
            else:
                cp.set(sec, opt, self.get_property(prop.name))
        with open(cfg, 'w+') as f:
            cp.write(f)
    def do_reduction(self, exposure):
        settings = DataReductionSettings(self)
        self._next_jobidx += 1
        self._inqueue.put((exposure, self._next_jobidx, settings))
        return self._next_jobidx
