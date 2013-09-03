from gi.repository import Gtk
import sastool
import collections
import ConfigParser
# from .spec_filechoosers import ExposureLoader, FileEntryWithButton

class PleaseWaitDialog(Gtk.Dialog):
    def __init__(self, title='Data reduction running, please wait...', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        vb = self.get_content_area()
        self.pbar = Gtk.ProgressBar()
        self.pbar.set_text('Working...')
        self.label = Gtk.Label()
        self.label.set_line_wrap(True)
        vb.pack_start(self.pbar, False, True, 0)
        vb.pack_start(self.label, True, True, 0)
        vb.show_all()
    def set_label_text(self, msg):
        self.label.set_text(msg)
        self.pbar.pulse()
        
class PleaseWaitInfoBar(Gtk.InfoBar):
    def __init__(self, buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.InfoBar.__init__(self)
        for i in range(len(buttons) / 2):
            self.add_button(buttons[2 * i], buttons[2 * i + 1])
        self.set_message_type(Gtk.MessageType.INFO)
        vb = self.get_content_area()
        self.label = Gtk.Label('Data reduction running...')
        self.pbar = Gtk.ProgressBar()
        self.pbar.set_text('Working...')
        vb.pack_start(self.label, False, True, 0)
        vb.pack_start(self.pbar, False, True, 0)
        self.show_all()
    def set_label_text(self, msg):
        self.pbar.set_text(msg)
        self.pbar.pulse()
    def set_n_jobs(self, n):
        self.label.set_text('%d data reduction job(s) running...' % n)

