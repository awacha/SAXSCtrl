import sastool
import sastool.misc.numerictests as smn
import os
import logging
from gi.repository import GObject
import queue
import threading
import weakref
from gi.repository import GLib
import matplotlib.figure
import matplotlib.backends.backend_agg
import time
import traceback
import numpy as np

from .subsystem import SubSystem, SubSystemError
from ...utils import objwithgui
from inspect import ArgSpec

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DataReductionError(SubSystemError):
    pass


class ExposureFlaggedException(Exception):
    pass


class DataReductionStep(objwithgui.ObjWithGUI):

    def __init__(self, chain):
        objwithgui.ObjWithGUI.__init__(self)
        self.chain = weakref.proxy(chain)

    def execute(self, exposure, force=False):
        """Carry out the data reduction step on exposure.

        Inputs:
            exposure: an instance of SASExposure
            force: if False, we will try to use already reduced data, e.g. for background
                subtraction or absolute intensity scaling. If True, these will be
                disregarded, reduction will once again be carried out on them.

        Should return:
            True if processing is to be continued with the next step
            False if processing should end here (e.g. we do not want to subtract background
                from empty beam measurements)
        """
        raise NotImplementedError

    def idlefunc(self):
        pass

    def message(self, exposure, mesg):
        # self.chain._threadsafe_emit('message', exposure['FSN'], mesg)
        logger.debug('Reducing #%d: %s' % (exposure['FSN'], mesg))


class BackgroundSubtraction(DataReductionStep):
    enable = GObject.property(type=bool, default=True, blurb='Enabled')
    title = GObject.property(
        type=str, default='Empty_beam', blurb='Title of background measurements')
    distance_tolerance = GObject.property(
        type=float, default=30, blurb='Distance tolerance (mm)', minimum=0)
    energy_tolerance = GObject.property(
        type=float, default=1, blurb='Energy tolerance (eV)', minimum=0)

    def __init__(self, chain):
        self._OWG_init_lists()
        self._OWG_hints['enable'] = {objwithgui.OWG_Hint_Type.OrderPriority: 0}
        self._OWG_hints['title'] = {objwithgui.OWG_Hint_Type.OrderPriority: 1}
        self._OWG_hints['distance_tolerance'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 3}
        self._OWG_hints['energy_tolerance'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 4}
        DataReductionStep.__init__(self, chain)
        self._lastemptybeamexposure = None

    def execute(self, exposure, force=False):
        if not self.enable:
            self.message(exposure, 'Skipping background subtraction.')
            return True
        if exposure['Title'] == self.title:
            self.message(
                exposure, 'Not subtracting background from background.')
            logger.debug('Storing exposure as last empty beam: %s' %
                         str(exposure.header))
            self._lastemptybeamexposure = exposure
            return False
        else:
            self.message(exposure, 'Title == ' + self.title)
        if self._lastemptybeamexposure is None:
            raise DataReductionError('No background exposure seen yet!')
        if ((abs(float(self._lastemptybeamexposure['EnergyCalibrated']) -
                 float(exposure['EnergyCalibrated'])) > self.energy_tolerance) or
            (abs(float(self._lastemptybeamexposure['DistCalibrated']) -
                 float(exposure['DistCalibrated'])) > self.distance_tolerance)):
            raise DataReductionError(
                'Last seen background (FSN=%d) does not match ' %
                (self._lastemptybeamexposure['FSN']) + str(exposure.header))
        self.message(
            exposure, 'Using background: #%(FSN)d, %(Title)s, %(DistCalibrated).2f mm, %(EnergyCalibrated).2f eV.' % self._lastemptybeamexposure)
        exposure -= self._lastemptybeamexposure
        exposure.header.add_history(
            'Subtracted background: #%(FSN)d, %(Title)s, %(DistCalibrated).2f mm, %(EnergyCalibrated).2f eV.' % self._lastemptybeamexposure)
        exposure.header.add_history('Maximum relative error: %g' % (
            np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
        exposure['FSNempty'] = self._lastemptybeamexposure['FSN']
        self.message(exposure, 'Background subtraction done.')
        return True


class AbsoluteCalibration(DataReductionStep):
    enable = GObject.property(type=bool, default=True, blurb='Enabled')
    title = GObject.property(
        type=str, default='Glassy_Carbon', blurb='Title of reference measurements')
    distance_tolerance = GObject.property(
        type=float, default=30, blurb='Distance tolerance (mm)')
    energy_tolerance = GObject.property(
        type=float, default=1, blurb='Energy tolerance (eV)')
    reference_datafile = GObject.property(
        type=str, default='', blurb='Path to reference dataset')

    def __init__(self, chain):
        self._OWG_init_lists()
        self._OWG_hints['enable'] = {objwithgui.OWG_Hint_Type.OrderPriority: 0}
        self._OWG_hints['title'] = {objwithgui.OWG_Hint_Type.OrderPriority: 1}
        self._OWG_hints['distance-tolerance'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 3}
        self._OWG_hints['energy-tolerance'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 4}
        self._OWG_hints['reference-datafile'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 5}
        self._OWG_entrytypes[
            'reference-datafile'] = objwithgui.OWG_Param_Type.File

        DataReductionStep.__init__(self, chain)
        self._lastgcexposure = None

    def execute(self, exposure, force=False):
        if not self.enable:
            return True
        if exposure['Title'] == self.title:
            self.message(
                exposure, 'Determining absolute scaling factor from measurement')
            # we are dealing with an absolute standard
            try:
                refdata = sastool.classes.SASCurve(self.reference_datafile)
            except IOError:
                raise DataReductionError(
                    'Cannot open reference data file ' + self.reference_datafile + ': ' + traceback.format_exc())
            try:
                logger.debug('Doing radial average from measured GC data.')
                logger.debug('Exposure.min(): %g' % exposure.Intensity.min())
                logger.debug('Exposure.max(): %g' % exposure.Intensity.max())
                measdata = exposure.radial_average(
                    refdata.q).sanitize(minval=1e-100, fieldname='q')
                logger.debug('Measdata len: %d' % len(measdata))
                logger.debug('measdata qmin: %g' % measdata.q.min())
                logger.debug('measdata qmax: %g' % measdata.q.max())
            except sastool.SASExposureException as see:
                raise DataReductionError(
                    'Could not make a radial average from the reference measurement: ' + traceback.format_exc())
            logger.debug('Interpolating refdata to measdata.q')
            refdata = refdata.interpolate(measdata.q)
            logger.debug('Interpolation done. Refdata len: %d' % len(refdata))
            self.message(exposure, 'Common q-range: %.4f to %.4f (%d points)' %
                         (refdata.q.min(), refdata.q.max(), len(refdata.q)))
            logger.debug('Determining scalefactor')
            scalefactor = measdata.scalefactor(refdata)
            self.message(
                exposure, 'Absolute intensity factor: %s' % scalefactor)
            exposure *= scalefactor
            exposure['NormFactor'] = float(scalefactor)
            exposure['NormFactorError'] = float(scalefactor.err)
            exposure.header.add_history(
                'Normalized into absolute intensity units using reference file %s' % self.reference_datafile)
            exposure.header.add_history('Maximum relative error: %g' % (
                np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
            f = matplotlib.figure.Figure()
            canvas = matplotlib.backends.backend_agg.FigureCanvasAgg(f)
            ax = f.add_subplot(1, 1, 1)
            refdata.loglog('bo', axes=ax, label='Reference')
            (measdata * scalefactor).loglog('r.', axes=ax,
                                            label='Measured, scaled (#%d)' % exposure['FSN'])
            ax.set_title('Norming factor: ' + str(scalefactor))
            ax.legend()
            ax.grid()
            canvas.draw()
            canvas.print_figure(
                os.path.join(self.chain.filessubsystem.eval2dpath, 'absint_%s.png' % os.path.split(exposure['FileName'])[1]), dpi=300)
            del canvas
            del f
            self._lastgcexposure = exposure
            return True
        if self._lastgcexposure is None:
            raise DataReductionError(
                'No intensity reference exposure seen yet!')
        if ((abs(float(self._lastgcexposure['EnergyCalibrated']) -
                 float(exposure['EnergyCalibrated'])) > self.energy_tolerance) or
            (abs(float(self._lastgcexposure['DistCalibrated']) -
                 float(exposure['DistCalibrated'])) > self.distance_tolerance)):
            raise DataReductionError(
                'Last seen intensity reference (FSN=%d) does not match ' %
                (self._lastgcexposure['FSN']) + str(exposure.header))
        self.message(
            exposure, 'Using intensity reference: #%(FSN)d, %(Title)s, %(DistCalibrated).2f mm, %(EnergyCalibrated).2f eV.' % self._lastgcexposure)
        exposure *= sastool.misc.ErrorValue(
            self._lastgcexposure['NormFactor'], self._lastgcexposure['NormFactorError'])
        exposure['FSNref1'] = self._lastgcexposure['FSN']
        exposure['NormFactor'] = self._lastgcexposure['NormFactor']
        exposure['NormFactorError'] = self._lastgcexposure['NormFactorError']
        exposure.header.add_history(
            'Used absolute intensity reference for scaling: #%(FSN)d, %(Title)s, %(DistCalibrated).2f mm, %(EnergyCalibrated).2f eV.' % self._lastgcexposure)
        exposure.header.add_history('Maximum relative error: %g' % (
            np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
        self.message(exposure, 'Scaled into absolute intensity units.')
        return True


class CorrectGeometry(DataReductionStep):
    solidangle = GObject.property(
        type=bool, default=True, blurb='Solid-angle correction')
    angle_dependent_self_absorption = GObject.property(
        type=bool, default=True, blurb='Angle-dependence of self-absorption')
    angle_dependent_air_absorption = GObject.property(
        type=bool, default=True,
        blurb='Angle-dependent air absorption in the flight path')
    angle_dependent_air_absorption_mu0 = GObject.property(
        type=float, default=1 / 88.349, minimum=0,
        blurb='Absorption coefficient of flight path gas at 1000 mbar (1/cm)')

    def __init__(self, chain):
        DataReductionStep.__init__(self, chain)

    def execute(self, exposure, force=False):
        if self.solidangle:
            exposure *= sastool.ErrorValue(*sastool.utils2d.corrections.solidangle_errorprop(
                exposure.tth, exposure.dtth, exposure['DistCalibrated'], exposure['DistCalibratedError']))
            exposure.header.add_history('Solid-angle correction done.')
            exposure.header.add_history('Maximum relative error: %g' % (
                np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
            self.message(exposure, 'Solid-angle correction done.')
        if self.angle_dependent_self_absorption:
            exposure *= sastool.ErrorValue(*sastool.utils2d.corrections.angledependentabsorption_errorprop(
                exposure.tth, exposure.dtth, exposure['Transm'], exposure['TransmError']))
            exposure.header.add_history(
                'Corrected for angle-dependence of self-absorption.')
            exposure.header.add_history('Maximum relative error: %g' % (
                np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
            self.message(
                exposure, 'Corrected for angle-dependence of self-absorption')
        if self.angle_dependent_air_absorption:
            if 'Vacuum' not in exposure.header:
                exposure.header.add_history(
                    'Could not carry out angle dependent air absorption correction: Vacuum value not known in header.')
                exposure.header.add_history('Maximum relative error: %g' % (
                    np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
            else:
                mu = self.angle_dependent_air_absorption_mu0 / \
                    1000.0 * exposure['Vacuum'] * 0.1
                exposure *= sastool.ErrorValue(*sastool.utils2d.corrections.angledependentairtransmission_errorprop(
                    exposure.tth, exposure.dtth, mu, 0, exposure['DistCalibrated'], exposure['DistCalibratedError']))
                exposure.header.add_history(
                    'Flight-path air absorption correction done.')
                exposure.header.add_history('Maximum relative error: %g' % (
                    np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
            return True


class PreScaling(DataReductionStep):
    transmission = GObject.property(
        type=bool, default=True, blurb='Divide by transmission')
    monitor = GObject.property(
        type=bool, default=True, blurb='Normalize by monitor')
    monitorname = GObject.property(
        type=str, default='MeasTime', blurb='Monitor counter name')

    def __init__(self, chain):
        DataReductionStep.__init__(self, chain)

    def execute(self, exposure, force=False):
        if self.monitor:
            monitor = sastool.ErrorValue(
                exposure[self.monitorname], exposure[self.monitorname + 'Error'])
            exposure /= monitor
            exposure.header.add_history(
                'Normalized by monitor %s' % self.monitorname)
            exposure.header.add_history('Maximum relative error: %g' % (
                np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
            self.message(exposure, 'Normalized by monitor %s' %
                         self.monitorname)
        if self.transmission:
            transm = sastool.ErrorValue(
                exposure['Transm'], exposure['TransmError'])
            exposure /= transm
            exposure.header.add_history(
                'Normalized by transmission: %s' % transm)
            exposure.header.add_history('Maximum relative error: %g' % (
                np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
            self.message(exposure, 'Normalized by transmission.')
        return True


class PostScaling(DataReductionStep):
    thickness = GObject.property(
        type=bool, default=True, blurb='Divide by thickness')

    def __init__(self, chain):
        DataReductionStep.__init__(self, chain)

    def execute(self, exposure, force=False):
        if self.thickness:
            thickness = sastool.ErrorValue(
                exposure['Thickness'], exposure['ThicknessError'])
            exposure /= thickness
            self.message(exposure, 'Divided by thickness: %.4f cm' %
                         exposure['Thickness'])
            exposure.header.add_history('Divided by thickness')
            exposure.header.add_history('Maximum relative error: %g' % (
                np.nanmax((exposure.Error / exposure.Intensity)[exposure.mask.mask == 1])))
        return True


class Saving(DataReductionStep):
    save2dcorr = GObject.property(
        type=bool, default=True, blurb='Save corrected 2d images')
    save1d = GObject.property(
        type=bool, default=True, blurb='Save radial averages (I(q) curves)')
    pixels_per_qbin = GObject.property(
        type=float, minimum=0, default=1, blurb='Number of pixels in a q-bin')

    def execute(self, exposure, force=False):
        if self.save2dcorr:
            self.chain.filessubsystem.writereduced(exposure)
            self.message(exposure, 'Saved corrected 2D image.')
        if self.save1d:
            self.chain.filessubsystem.writeradial(
                exposure, self.pixels_per_qbin)
            self.message(exposure, 'Saved radial averaged curve (pixels per q bin: %.2f).' %
                         self.pixels_per_qbin)
        return True


class ReductionThread(GObject.GObject):
    __gtype_name__ = 'SAXSCtrl_ReductionThread'
    __gsignals__ = {
        'message': (GObject.SignalFlags.RUN_FIRST, None, (int, str)),
        'done': (GObject.SignalFlags.RUN_FIRST, None, (int, object,)),
        'idle': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'endthread': (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, parent):
        GObject.GObject.__init__(self)
        self.inqueue = queue.Queue()
        self.chain = []
        self._thread = threading.Thread(target=self.run)
        self._thread.daemon = True
        self._thread.start()
        self.parent = parent
        self.filessubsystem = parent.credo().subsystems['Files']

    def add_step(self, step):
        self.chain.append(step(self))

    def run(self):
        while True:
            try:
                fsn, force = self.inqueue.get(block=True, timeout=0.5)
            except queue.Empty:
                self._threadsafe_emit('idle')
                fsn, force = self.inqueue.get()
            if isinstance(fsn, str) and fsn == 'KILL!':
                break
            try:
                exposure = self.parent.load_exposure(fsn)
                try:
                    if exposure.header['ErrorFlags']:
                        raise ExposureFlaggedException
                except KeyError:
                    # 'ErrorFlags' key not in header: this exposure has not been flagged
                    pass
                exposure = self.execute(exposure, force, None)
            except ExposureFlaggedException:
                self._threadsafe_emit('message', exposure[
                                      'FSN'], 'Not running data reduction: this exposure is flagged as erroneous.')
            except Exception as ex:
                logger.error(
                    'Error while reducing FSN #%d: ' % fsn + str(traceback.format_exc()))
            self._threadsafe_emit('done', exposure['FSN'], exposure.header)
        self._threadsafe_emit('endthread')

    def _threadsafe_emit(self, signalname, *args):
        GLib.idle_add(lambda sn, arglist: bool(
            self.emit(sn, *arglist)) and False, signalname, args)

    def execute(self, exposure, force=False, endstepclassname=None):
        logger.debug('Starting execution of %s. Force: %d. Endstepclassname: %s' %
                     (str(exposure.header), force, str(endstepclassname)))
        for c in self.chain:
            if not c.execute(exposure, force):
                break
            if c.__class__.__name__ == endstepclassname:
                break
        logger.debug('Done execution of %s.' % str(exposure.header))
        return exposure

    def kill(self):
        try:
            while True:
                self.inqueue.get_nowait()
        except queue.Empty:
            pass
        self.inqueue.put(('KILL!', True))
        self._thread.join()
        self._thread = None

    def stop(self):
        try:
            while True:
                self.inqueue.get_nowait()
        except queue.Empty:
            pass

    def reduce(self, fsn, force=False):
        self.inqueue.put_nowait((fsn, force))


class SubSystemDataReduction(SubSystem):
    __gsignals__ = {
        'message': (GObject.SignalFlags.RUN_FIRST, None, (int, str)),
        'done': (GObject.SignalFlags.RUN_FIRST, None, (int, object)),
        'idle': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'notify': 'override'}
    filebegin = GObject.property(
        type=str, nick='IO::File_begin', blurb='Filename prefix', default='crd')
    ndigits = GObject.property(
        type=int, nick='IO::Number_digits', blurb='Number of digits in FSN', default=5, minimum=1)
    __propvalues__ = None
    _reduction_thread = None

    def __init__(self, credo, offline=True):
        SubSystem.__init__(self, credo, offline)
        ssf = self.credo().subsystems['Files']
        self._reduction_thread = None
        self._OWG_init_lists()

        self._OWG_nogui_props.append('configfile')
        self._OWG_hints['filebegin'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 0}
        self._OWG_hints['ndigits'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 1}
        self._restart_reductionthread()

    def __del__(self):
        try:
            self._reduction_thread.kill()
        except AttributeError:
            pass

    def _restart_reductionthread(self):
        logger.debug('(Re)starting reduction thread')
        if self._reduction_thread is not None:
            for c in self._thread_connections:
                self._reduction_thread.disconnect(c)
            self._thread_connections = []
            self._reduction_thread.kill()
            self._reduction_thread = None
            self._OWG_parts = []
        self._reduction_thread = ReductionThread(self)
        self._thread_connections = [
            self._reduction_thread.connect('endthread', self._on_endthread),
            self._reduction_thread.connect('idle', self._on_idle),
            self._reduction_thread.connect('message', self._on_message),
            self._reduction_thread.connect('done', self._on_done)]
        self._OWG_parts = self._reduction_thread.chain
        self.add_step(PreScaling)
        self.add_step(BackgroundSubtraction)
        self.add_step(CorrectGeometry)
        self.add_step(PostScaling)
        self.add_step(AbsoluteCalibration)
        self.add_step(Saving)
        self.loadstate(self.credo().getstatefile())

    def load_exposure(self, fsn):
        ssf = self.credo().subsystems['Files']
        return sastool.SASExposure(ssf.get_exposureformat(self.filebegin, self.ndigits) % fsn, dirs=ssf.rawloadpath)

    def load_header(self, fsn):
        ssf = self.credo().subsystems['Files']
        return sastool.SASHeader(ssf.get_headerformat(self.filebegin, self.ndigits) % fsn, dirs=ssf.rawloadpath)

    def add_step(self, step):
        self._reduction_thread.add_step(step)

    def reduce(self, fsn, force=False):
        if self._reduction_thread is None:
            self._restart_reductionthread()
        self._reduction_thread.reduce(fsn, force)

    def _on_endthread(self, thread):
        for c in self._thread_connections:
            self._reduction_thread.disconnect(c)
        del self._reduction_thread
        self._reduction_thread = None

    def _on_message(self, thread, fsn, message):
        logger.info('Processing FSN #%d: %s' % (fsn, message))
        self.emit('message', fsn, message)

    def _on_idle(self, thread):
        self.emit('idle')

    def _on_done(self, thread, fsn, exposure):
        self.emit('done', fsn, exposure)

    def __del__(self):
        if self._reduction_thread is not None:
            self._reduction_thread.kill()

    def stop(self):
        self._reduction_thread.stop()
