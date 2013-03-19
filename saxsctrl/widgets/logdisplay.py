from gi.repository import Gtk
from gi.repository import GObject
import logging
import logging.handlers

class LogDisplay(Gtk.VBox):
    def __init__(self, *args, **kwargs):
        Gtk.VBox.__init__(self, *args, **kwargs)
        self.textview = Gtk.TextView()
        self.textbuffer = self.textview.get_buffer()
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(sw, True, True, 0)
        sw.add(self.textview)
        self.tags = {'ERROR':self.textbuffer.create_tag('ERROR', foreground='red'),
                   'WARNING':self.textbuffer.create_tag('WARNING', foreground='orange'),
                   '__DEFAULT__':self.textbuffer.create_tag('__DEFAULT__', foreground='black'),
                   }
    def addlogline(self, message, record):
        if record.levelno >= logging.ERROR:
            tag = self.tags['ERROR']
        elif record.levelno >= logging.WARNING:
            tag = self.tags['WARNING']
        else:
            tag = self.tags['__DEFAULT__']
        enditer = self.textview.get_buffer().get_end_iter()
        self.textview.get_buffer().insert_with_tags(enditer, message + '\n', tag)
        self.textview.scroll_to_iter(enditer, 0, False, 0, 0)
        return False
    
class Gtk3LogHandler(logging.Handler):
    def __init__(self, logdisplay=None):
        logging.Handler.__init__(self)
        self.logdisplay = logdisplay
    def emit(self, record):
        message = self.format(record)
        GObject.idle_add(self.logdisplay.addlogline, message, record)
        # logdisplay.addlogline(message, record)
        
