from .subsystem import SubSystem, SubSystemError
from gi.repository import GObject
from ...utils.objwithgui import ObjWithGUI, OWG_Hint_Type


class SubSystemCollimation(SubSystem):
    aperture1 = GObject.property(
        type=float, blurb='PH#1 aperture diameter (um)', minimum=0, default=300.)
    aperture2 = GObject.property(
        type=float, blurb='PH#2 aperture diameter (um)', minimum=0, default=300.)
    aperture3 = GObject.property(
        type=float, blurb='PH#3 aperture diameter (um)', minimum=0, default=300.)
    l0 = GObject.property(
        type=float, blurb='Source-PH#1 distance (mm)', minimum=0, default=200.)
    l1 = GObject.property(
        type=float, blurb='PH#1-PH#2 distance (mm)', minimum=0, default=300.)
    l2 = GObject.property(
        type=float, blurb='PH#2-PH#3 distance (mm)', minimum=0, default=300.)
    ls = GObject.property(
        type=float, blurb='PH#3-sample distance (mm)', minimum=0, default=130)
    lbs = GObject.property(
        type=float, blurb='Beamstop-detector distance (mm)', minimum=0, default=54)
    dbs = GObject.property(
        type=float, blurb='Beamstop diameter (mm)', minimum=0, default=4)
    beamstop_in_ymin = GObject.property(
        type=float, blurb='Lower Y coordinate of beamstop in (mm)', default=0)
    beamstop_in_ymax = GObject.property(
        type=float, blurb='Upper Y coordinate of beamstop in (mm)', default=5)
    beamstop_out_yrel = GObject.property(
        type=float, blurb='Beamstop out relative position (mm)', default=10)
    motor_beamstopx = GObject.property(
        type=str, default='BeamStop_X', blurb='Motor name for horizontal beamstop positioning')
    motor_beamstopy = GObject.property(
        type=str, default='BeamStop_Y', blurb='Motor name for vertical beamstop positioning')
    motor_ph1x = GObject.property(
        type=str, default='PH1_X', blurb='Motor name for horizontal positioning of pinhole #1')
    motor_ph1y = GObject.property(
        type=str, default='PH1_Y', blurb='Motor name for vertical positioning of pinhole #1')
    motor_ph2x = GObject.property(
        type=str, default='PH2_X', blurb='Motor name for horizontal positioning of pinhole #2')
    motor_ph2y = GObject.property(
        type=str, default='PH2_Y', blurb='Motor name for vertical positioning of pinhole #2')
    motor_ph3x = GObject.property(
        type=str, default='PH3_X', blurb='Motor name for horizontal positioning of pinhole #3')
    motor_ph3y = GObject.property(
        type=str, default='PH3_Y', blurb='Motor name for vertical positioning of pinhole #3')

    def __init__(self, *args, **kwargs):
        SubSystem.__init__(self, *args, **kwargs)
        self._OWG_init_lists()

        self._OWG_nogui_props.append('configfile')
        for i, par in enumerate(['l0', 'l1', 'l2', 'aperture1', 'aperture2',
                                 'aperture3', 'ls', 'lbs', 'dbs',
                                 'beamstop-in-ymin', 'beamstop-in-ymax', 'beamstop-out-y',
                                 'motor-beamstopx', 'motor-beamstopy',
                                 'motor-ph1x', 'motor-ph1y', 'motor-ph2x',
                                 'motor-ph2y', 'motor-ph3x', 'motor-ph3y']):
            self._OWG_hints[par] = {OWG_Hint_Type.OrderPriority: i}
