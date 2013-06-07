from gi.repository import GObject

__all__ = ['SubSystemExposure']


class SubSystemExposure(GObject.GObject):
    __gsignals__ = {'exposure-done':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'exposure-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'exposure-end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)), }
    exptime = GObject.property(type=float, minimum=0, default=1)
    dwelltime = GObject.property(type=float, minimum=0.003, default=0.003)
    nimages = GObject.property(type=int, minimum=1, default=1)
    def __init__(self, pilatus, genix, exptime, dwelltime, nimages):
        GObject.GObject.__init__(self)
        self.pilatus = pilatus
        self.genix = genix
    def start(self):
        pass
