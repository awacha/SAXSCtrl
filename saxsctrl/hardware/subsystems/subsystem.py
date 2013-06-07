import weakref
from gi.repository import GObject

class SubSystem(GObject.GObject):
    def __init__(self, credo):
        GObject.GObject.__init__(self)
        self.credo = weakref(credo)
    def loadstate(self, configparser):
        pass
    def savestate(self, configparser):
        pass
