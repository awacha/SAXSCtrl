from gi.repository import Gtk
from gi.repository import GObject
from .widgets import ToolDialog

class SequenceElementEditor(Gtk.Dialog):
    def __init__(self):
        Gtk.Dialog.__init__(self)

class SAXSSequence(ToolDialog):
    def __init__(self, credo, title='SAXS Sequence'):
        ToolDialog.__init__(self, credo, title)
        
        self.sequence = Gtk.ListStore(GObject.TYPE_STRING,  # sample name
                                    )
