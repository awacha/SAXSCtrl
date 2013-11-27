from .subsystem import SubSystem, SubSystemError
from gi.repository import GObject

class PinHole(GObject.GObject):
    index = GObject.property(type=int, default=0, blurb='Pin-hole index')
    motor_x = GObject.property(type=str, default='', blurb='Horizontal positioner')
    motor_y = GObject.property(type=str, default='', blurb='Vertical positioner')
    z_pos = GObject.property(type=float, default=0, blurb='Position along optical axis')
    holes = None
    def __init__(self, credo):
        GObject.GObject.__init__(self)
        self.credo = credo
        self.clear_holes()
    def add_hole(self, posx, posy, diameter):
        pass
    def remove_hole(self, posx=None, posy=None, diameter=None):
        pass
    def clear_holes(self):
        self.holes = []
    
class BeamStop(GObject.GObject):
    diameter = GObject.property(type=float, default=3, minimum=0, blurb='Diameter of beam-stop (mm)')
    dist_holder_from_det = GObject.property(type=float, default=14, minimum=0, blurb='Distance of the holder from the detector sensor (mm)')
    length = GObject.property(type=float, default=10, minimum=0, blurb='Length from the face to the holder (mm)')
    motor_x = GObject.property(type=str, default='', blurb='Horizontal positioner')
    motor_y = GObject.property(type=str, default='', blurb='Vertical positioner')
    def __init__(self, credo):
        GObject.GObject.__init__(self)
        self.credo = credo

class SampleEnvironment(GObject.GObject):
    len_before_sample = GObject.property(type=float, default=0, minimum=0, blurb='Length before sample (mm)')
    len_after_sample = GObject.property(type=float, default=0, minimum=0, blurb='Length after sample (mm)')
    in_vacuum = GObject.property(type=bool, default=True, blurb='Evacuated?')
    def __init__(self, credo):
        GObject.GObject.__init__(self)
        self.credo = credo

class FlightTube(GObject.GObject):
    length = GObject.property(type=float, default=0, minimum=0, blurb='Length of flight path (mm)')
    def __init__(self, credo):
        GObject.GObject.__init__(self)
        self.credo = credo

class SubSystemGeometry(SubSystem):
    pinholes = None
    source = None
    sampleenvironment = None
    beamstop = None
    detector = None
    flighttube = None
    def loadstate(self, configparser, sectionprefix=''):
        SubSystem.loadstate(self, configparser, sectionprefix)
        
    def savestate(self, configparser, sectionprefix=''):
        SubSystem.savestate(self, configparser, sectionprefix)
    