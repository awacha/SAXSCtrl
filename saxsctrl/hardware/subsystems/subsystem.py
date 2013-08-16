import weakref
from gi.repository import GObject
from ...utils import objwithgui

class SubSystemError(StandardError):
    pass

class SubSystemException(Exception):
    pass

class SubSystem(objwithgui.ObjWithGUI):
    configfile = GObject.property(type=str, default='', blurb='Configuration file')
    offline = GObject.property(type=bool, default=True, blurb='Offline mode')
    def __init__(self, credo, offline=True):
        self._OWG_init_lists()
        self._OWG_entrytypes['configfile'] = objwithgui.OWG_Param_Type.File
        self._OWG_nogui_props.append('offline')
        self._OWG_nosave_props.append('offline')
        objwithgui.ObjWithGUI.__init__(self)
        self.credo = weakref.ref(credo)
        self.offline = offline
    def _get_classname(self):
        return self.__class__.__name__.replace('SubSystem', '')
    def destroy(self):
        pass
