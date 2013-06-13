from gi.repository import GObject
from .subsystem import SubSystem, SubSystemException

__all__ = ['SubSystemTransmission']

class SubSystemTransmission(SubSystem):
    __gsignals__ = {}
    
    def __init__(self, credo):
        SubSystem.__init__(self, credo)
