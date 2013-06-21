from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Pango
import logging
import logging.handlers

class LogDisplay(Gtk.VBox):
    def __init__(self, *args, **kwargs):
        Gtk.VBox.__init__(self, *args, **kwargs)
        self.textview = Gtk.TextView()
        self.textbuffer = self.textview.get_buffer()
        self.textview.set_editable(False)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(sw, True, True, 0)
        sw.add(self.textview)
        self.tags = {'ERROR':self.textbuffer.create_tag('ERROR', foreground='red'),
                   'WARNING':self.textbuffer.create_tag('WARNING', foreground='orange'),
                   '__DEFAULT__':self.textbuffer.create_tag('__DEFAULT__', foreground='black'),
                   'CRITICAL':self.textbuffer.create_tag('CRITICAL', foreground='black', background='red')
                   }
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(hb, False, False, 0)
        self.image = Gtk.Image()
        hb.pack_start(self.image, False, False, 0)
        self.label = Gtk.Label(); self.label.set_alignment(0, 0.5)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        hb.pack_start(self.label, True, True, 0)
        self.show_all()
    def addlogline(self, message, record):
        if record.levelno >= logging.CRITICAL:
            tag = self.tags['CRITICAL']
        elif record.levelno >= logging.ERROR:
            tag = self.tags['ERROR']
        elif record.levelno >= logging.WARNING:
            tag = self.tags['WARNING']
        else:
            tag = self.tags['__DEFAULT__']
        enditer = self.textview.get_buffer().get_end_iter()
        self.textview.get_buffer().insert_with_tags(enditer, message + '\n', tag)
        self.textview.scroll_mark_onscreen(self.textview.get_buffer().get_insert())
        if record.levelno >= logging.INFO:
            self.label.set_label(record.message)
        if record.levelno >= logging.CRITICAL:
            self.image.set_from_stock(Gtk.STOCK_STOP, Gtk.IconSize.SMALL_TOOLBAR)
        elif record.levelno >= logging.ERROR:
            self.image.set_from_stock(Gtk.STOCK_DIALOG_ERROR, Gtk.IconSize.SMALL_TOOLBAR)
        elif record.levelno >= logging.WARNING:
            self.image.set_from_stock(Gtk.STOCK_DIALOG_WARNING, Gtk.IconSize.SMALL_TOOLBAR)
        elif record.levelno >= logging.INFO:
            self.image.set_from_stock(Gtk.STOCK_DIALOG_INFO, Gtk.IconSize.SMALL_TOOLBAR)
        else:
            self.image.set_from_stock(Gtk.STOCK_OK, Gtk.IconSize.SMALL_TOOLBAR)
        return False
    
class Gtk3LogHandler(logging.Handler):
    def __init__(self, logdisplay=None):
        logging.Handler.__init__(self)
        self.logdisplay = logdisplay
    def emit(self, record):
        message = self.format(record)
        GObject.idle_add(self.logdisplay.addlogline, message, record)
        # logdisplay.addlogline(message, record)
        
