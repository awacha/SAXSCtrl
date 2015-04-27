from .subsystem import SubSystem, SubSystemError
from gi.repository import GObject
from ...utils.objwithgui import ObjWithGUI


class SubSystemCollimation(SubSystem):
    aperture1 = GObject.property(
        type=float, blurb='PH#1 aperture (um)', minimum=0, default=300.)
    aperture2 = GObject.property(
        type=float, blurb='PH#2 aperture (um)', minimum=0, default=300.)
    aperture3 = GObject.property(
        type=float, blurb='PH#3 aperture (um)', minimum=0, default=300.)
    l1 = GObject.property(
        type=float, blurb='PH#1-PH#2 distance (mm)', minimum=0, default=300.)
    l2 = GObject.property(
        type=float, blurb='PH#2-PH#3 distance (mm)', minimum=0, default=300.)
    ls = GObject.property(
        type=float, blurb='PH#3-sample distance (mm)', minimum=0, default=130)
    lbs = GObject.property(
        type=float, blurb='Beamstop-detector distance (mm)', minimum=0, default=54)
