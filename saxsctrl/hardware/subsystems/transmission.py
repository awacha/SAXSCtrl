from gi.repository import GObject
from .subsystem import SubSystem, SubSystemException
from ..instruments import genix
import os
import logging
import sastool
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
from ...utils import objwithgui
import numpy as np

__all__ = ['SubSystemTransmission']

class TransmissionException(SubSystemException):
    pass

class SubSystemTransmission(SubSystem):
    __gsignals__ = {'end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'dark':(GObject.SignalFlags.RUN_FIRST, None, (float, float, int)),
                    'empty':(GObject.SignalFlags.RUN_FIRST, None, (float, float, int)),
                    'sample':(GObject.SignalFlags.RUN_FIRST, None, (float, float, int)),
                    'transm':(GObject.SignalFlags.RUN_FIRST, None, (float, float, int)),
                    'notify':'override'}
    beamstop_in = GObject.property(type=float, default=7.4, blurb='Beam-stop in-beam position')
    beamstop_out = GObject.property(type=float, default=20, blurb='Beam-stop out-beam position')
    samplename = GObject.property(type=str, default='', blurb='Name of the sample')
    emptyname = GObject.property(type=str, default='Empty beam', blurb='Name of the empty beam')
    darkname = GObject.property(type=str, default='Dark', blurb='Name of dark current')
    countingtime = GObject.property(type=float, default=0.5, minimum=0, maximum=1e6, blurb='Counting time (sec)')
    dwelltime = GObject.property(type=float, default=0.003, minimum=0.003, maximum=1e6, blurb='Dwell time (sec)')
    mask = GObject.property(type=str, default='', blurb='Mask file')
    nimages = GObject.property(type=int, default=10, minimum=1, maximum=10000, blurb='Number of exposures')
    iterations = GObject.property(type=int, default=1, minimum=1, maximum=10000, blurb='Number of iterations')
    beamstop_motor = GObject.property(type=str, default='BeamStop_Y', blurb='Beam-stop motor name')
    method = GObject.property(type=str, default='max', blurb='Intensity counting method')
    move_beamstop_back_at_end = GObject.property(type=bool, default=True, blurb='Move beam-stop back at end')
    def __init__(self, credo, offline=True):
        self._OWG_init_lists()
        self._OWG_entrytypes['mask'] = objwithgui.OWG_Param_Type.File
        self._OWG_entrytypes['method'] = objwithgui.OWG_Param_Type.ListOfStrings
        self._OWG_hints['method'] = {objwithgui.OWG_Hint_Type.ChoicesList:['max', 'sum', 'mean']}
        self._ex_conn = []
        self._whatsnext = 'dark'
        self._mask = None
        self._kill = False
        SubSystem.__init__(self, credo, offline)
        if not self.mask:
            self.mask = self.credo().subsystems['Exposure'].default_mask
    def do_notify(self, prop):
        if prop.name == 'mask':
            if not os.path.isabs(self.mask):
                self.mask = os.path.join(self.credo().subsystems['Files'].maskpath, self.mask)
            else:
                self._mask = sastool.classes.SASMask(self.mask)
    def execute(self):
        self._kill = False
        mot = self.credo().subsystems['Motors'].get(self.beamstop_motor)
        g = self.credo().get_equipment('genix')
        if not g.is_idle():
            raise TransmissionException('X-ray source is busy.')
        if g.status != genix.GenixStatus.Standby:
            logger.info('Setting X-ray source to low-power mode.')
            g.do_standby()
            logger.info('Waiting for X-ray source to reach low-power mode.')
            g.wait_for_status(genix.GenixStatus.Standby, lambda :self._kill)
            if self._kill:
                raise TransmissionException('User break!')
            logger.info('Low-power mode reached.')
        else:
            logger.info('X-ray source is already at low-power mode.')
        mot.moveto(self.beamstop_out)
        logger.info('Moving beam-stop out of the beam.')
        self.credo().subsystems['Motors'].wait_for_idle()
        logger.info('Beam-stop is out of beam.')
        self._iterations_finished = 0
        self._I = np.zeros((self.iterations * self.nimages, 3))
        sse = self.credo().subsystems['Exposure']
        self._ex_conn = [sse.connect('exposure-image', self._on_image),
                         sse.connect('exposure-end', self._on_end)]
        sse.exptime = self.countingtime
        sse.dwelltime = self.dwelltime
        sse.nimages = self.nimages
        self.credo().subsystems['Files'].filebegin = 'tra'
        self._oldshuttermode = sse.operate_shutter
        self._kill = False
        self._do_iteration()
    def kill(self):
        logger.info('Kill requested in transmission sequence.')
        self._kill = True
        self.credo().subsystems['Exposure'].kill()
    def _on_image(self, sse, exposure):
        if self.method == 'max':
            self._I[self._iterations_finished * self.nimages + self._images_received, self._whatsnext] = exposure.max() / self.countingtime
        elif self.method == 'sum':
            self._I[self._iterations_finished * self.nimages + self._images_received, self._whatsnext] = exposure.sum() / self.countingtime
        elif self.method == 'mean':
            self._I[self._iterations_finished * self.nimages + self._images_received, self._whatsnext] = exposure.mean() / self.countingtime
        else:
            raise NotImplementedError(self.method)
        self._images_received += 1
    def _on_end(self, sse, status):
        logger.debug('Transmission: exposure ended.')
        if self._kill:
            status = False
        if not status:
            self.emit('end', False)
            return
        cts = self._I[:(self._iterations_finished + 1) * self.nimages, self._whatsnext]
        if self._whatsnext == 0:
            self.emit('dark', cts.mean(), cts.std(), len(cts))
        elif self._whatsnext == 1:
            self.emit('empty', cts.mean(), cts.std(), len(cts))
        elif self._whatsnext == 2:
            self.emit('sample', cts.mean(), cts.std(), len(cts))
            allcts = self._I[:(self._iterations_finished + 1) * self.nimages, :]
            dcts = allcts[:, 0]; ects = allcts[:, 1]; scts = allcts[:, 2]
            d = sastool.classes.ErrorValue(dcts.mean(), dcts.std())
            e = sastool.classes.ErrorValue(ects.mean(), ects.std())
            s = sastool.classes.ErrorValue(scts.mean(), scts.std())
            t = (s - d) / (e - d)
            self.emit('transm', t.val, t.err, len(scts))
        self._whatsnext += 1
        if self._whatsnext == 3:
            self._iterations_finished += 1
            self._do_iteration()
        else:
            logger.debug('Starting next exposure')
            self._do_exposure()
    def _do_iteration(self):
        if self._iterations_finished == self.iterations:
            self.emit('end', True)
            return
        if self._kill:
            self.emit('end', False)
            return
        logger.info('Transmission: starting iteration %d' % self._iterations_finished)
        self._whatsnext = 0
        self._do_exposure()
    def _do_exposure(self):
        if self._kill:
            self.emit('end', False)
            return
        sse = self.credo().subsystems['Exposure']
        if self._whatsnext == 0:  # 'dark'
            logger.info('Transmission: exposing dark.')
            sse.operate_shutter = False
        elif self._whatsnext == 1:  # 'empty'
            logger.info('Transmission: exposing empty.')
            sse.operate_shutter = True
            self.credo().subsystems['Samples'].set(self.emptyname)
            self.credo().subsystems['Samples'].moveto(blocking=True)
        elif self._whatsnext == 2:  # 'sample'
            sse.operate_shutter = True
            logger.info('Transmission: exposing sample.')
            self.credo().subsystems['Samples'].set(self.samplename)
            self.credo().subsystems['Samples'].moveto(blocking=True)
        else:
            raise NotImplementedError(self._whatsnext)
        logger.info('Transmission: starting exposure.')
        self._images_received = 0
        sse.start(mask=self._mask, write_nexus=False)
    def do_end(self, status):
        for c in self._ex_conn:
            self.credo().subsystems['Exposure'].disconnect(c)
        self.credo().subsystems['Exposure'].operate_shutter = self._oldshuttermode
        self._ex_conn = []
        if self.move_beamstop_back_at_end:
            mot = self.credo().subsystems['Motors'].get(self.beamstop_motor)
            mot.moveto(self.beamstop_in)
            logger.info('Moving beam-stop in the beam.')
            self.credo().subsystems['Motors'].wait_for_idle()
            logger.info('Beam-stop is in the beam.')
        else:
            logger.info('Beam-stop still out of beam.')
    def do_dark(self, mean, std, n):
        logger.debug('Intensity of dark current up to now: %d +/- %d (from %d exposures)' % (mean, std, n))
    def do_empty(self, mean, std, n):
        logger.debug('Intensity of empty beam up to now: %d +/- %d (from %d exposures)' % (mean, std, n))
    def do_sample(self, mean, std, n):
        logger.debug('Intensity of sample up to now: %d +/- %d (from %d exposures)' % (mean, std, n))
        
        
