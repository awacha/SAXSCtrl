import weakref
from gi.repository import GObject
from ...utils import objwithgui

class SubSystemError(StandardError):
    pass

class SubSystemException(Exception):
    pass

class SubSystem(objwithgui.ObjWithGUI):
    configfile = GObject.property(type=str, default='', blurb='Configuration file')
    def __init__(self, credo):
        self._OWG_init_lists()
        self._OWG_entrytypes['configfile'] = objwithgui.OWG_Param_Type.File
        objwithgui.ObjWithGUI.__init__(self)
        self.credo = weakref.ref(credo)
    def _get_classname(self):
        return self.__class__.__name__.replace('SubSystem', '')
    def destroy(self):
        pass
