from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import GLib

import logging


class LogDisplay(Gtk.VBox):
    def __init__(self, *args, **kwargs):
        Gtk.VBox.__init__(self, *args, **kwargs)
        self.textview = Gtk.TextView()
        self.textbuffer = self.textview.get_buffer()
        self.textbuffer.create_mark('log_end', self.textbuffer.get_end_iter(), False)
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
        self.label = Gtk.Label(); self.label.set_halign(Gtk.Align.START); self.label.set_valign(Gtk.Align.CENTER)
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
        enditer = self.textbuffer.get_end_iter()
        self.textbuffer.insert_with_tags(enditer, message + '\n', tag)
        self.textview.scroll_to_mark(self.textbuffer.get_mark('log_end'), 0.1, False, 0, 0)
        if record.levelno >= logging.INFO:
            self.label.set_label(record.message)
        if record.levelno >= logging.CRITICAL:
            self.image.set_from_icon_name('face-crying', Gtk.IconSize.SMALL_TOOLBAR)
        elif record.levelno >= logging.ERROR:
            self.image.set_from_icon_name('dialog-error', Gtk.IconSize.SMALL_TOOLBAR)
        elif record.levelno >= logging.WARNING:
            self.image.set_from_icon_name('dialog-warning', Gtk.IconSize.SMALL_TOOLBAR)
        elif record.levelno >= logging.INFO:
            self.image.set_from_icon_name('dialog-info', Gtk.IconSize.SMALL_TOOLBAR)
        else:
            # self.image.set_from_icon_name('OK', Gtk.IconSize.SMALL_TOOLBAR)
            pass
        return False

class Gtk3LogHandler(logging.Handler):
    def __init__(self, logdisplay=None):
        logging.Handler.__init__(self)
        self.logdisplay = logdisplay
    def emit(self, record):
        message = self.format(record)
        GLib.idle_add(self.logdisplay.addlogline, message, record)
        # logdisplay.addlogline(message, record)

