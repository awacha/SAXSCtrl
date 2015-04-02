from gi.repository import Gtk
from gi.repository import GLib

import os
import matplotlib.pyplot as plt
import shutil
import sastool
import threading
import re


class MovieMaker(Gtk.Dialog):
    def __init__(self, credo, scan, title='Create movie from scan', parent=None, flags=0, buttons=('Execute', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.CANCEL)
        self.credo = credo
        self.scan = scan
        vb = self.get_content_area()
        self.pritable = Gtk.Table()
        
        self.pri_frame = Gtk.Frame(label='Image boundary')
        vb.pack_start(self.pri_frame, False, True, 0)
        vb1 = Gtk.VBox()
        self.pri_frame.add(vb1)
        self.pri_checkbutton = Gtk.CheckButton('Respect boundary')
        vb1.pack_start(self.pri_checkbutton, True, True, 0)
        self.pri_checkbutton.connect('toggled', self.on_sensitivity_checkbutton, self.pritable)
        self.on_sensitivity_checkbutton(self.pri_checkbutton, self.pritable)
        vb1.pack_start(self.pritable, False, True, 0)
        row = 0
        
        l = Gtk.Label(label='Top:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        self.pritable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.pritop_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e10, 1e10, 1, 10), digits=2)
        self.pritable.attach(self.pritop_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Bottom:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        self.pritable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.pribottom_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e10, 1e10, 1, 10), digits=2)
        self.pritable.attach(self.pribottom_entry, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Left:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        self.pritable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.prileft_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e10, 1e10, 1, 10), digits=2)
        self.pritable.attach(self.prileft_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Right:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        self.pritable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.priright_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e10, 1e10, 1, 10), digits=2)
        self.pritable.attach(self.priright_entry, 1, 2, row, row + 1)
        row += 1

        self.entrytable = Gtk.Table()
        vb.pack_start(self.entrytable, False, True, 0)
        row = 0

        self.Imin_checkbutton = Gtk.CheckButton('Lower intensity cut-off:'); self.Imin_checkbutton.set_halign(Gtk.Align.START)
        self.entrytable.attach(self.Imin_checkbutton, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.Imin_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 1e100, 1, 10), digits=0)
        self.entrytable.attach(self.Imin_entry, 1, 2, row, row + 1)
        self.Imin_checkbutton.connect('toggled', self.on_sensitivity_checkbutton, self.Imin_entry)
        self.on_sensitivity_checkbutton(self.Imin_checkbutton, self.Imin_entry)
        row += 1
        
        self.Imax_checkbutton = Gtk.CheckButton('Upper intensity cut-off:'); self.Imax_checkbutton.set_halign(Gtk.Align.START)
        self.entrytable.attach(self.Imax_checkbutton, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.Imax_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 1e100, 1, 10), digits=0)
        self.entrytable.attach(self.Imax_entry, 1, 2, row, row + 1)
        self.Imax_checkbutton.connect('toggled', self.on_sensitivity_checkbutton, self.Imax_entry)
        self.on_sensitivity_checkbutton(self.Imax_checkbutton, self.Imax_entry)
        row += 1

        l = Gtk.Label(label='Colour scaling:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.colourscale_combo = Gtk.ComboBoxText()
        for l in ['linear', 'log', 'sqrt']:
            self.colourscale_combo.append_text(l)
        self.colourscale_combo.set_active(0)
        self.entrytable.attach(self.colourscale_combo, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Movie fps:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.fps_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(25, 0, 100, 1, 10), digits=0)
        self.fps_entry.set_value(25)
        self.entrytable.attach(self.fps_entry, 1, 2, row, row + 1)
        vb.show_all()
        
        self.progress = Gtk.ProgressBar()
        # self.get_action_area().pack_start(self.progress, False,True,0)
        vb.pack_start(self.progress, False, True, 0)

        self.connect('response', self.on_response)
        self._userbreak = False
    def on_sensitivity_checkbutton(self, checkbutton, widget):
        widget.set_sensitive(checkbutton.get_active())
    def on_response(self, dialog, respid):
        if respid == Gtk.ResponseType.CANCEL:
            self._userbreak = True
            return
        elif respid == Gtk.ResponseType.DELETE_EVENT:
            return
        else:
            self.on_run()
            return
    def on_run(self):
        fig = plt.figure()
        self.pri_frame.set_sensitive(False)
        self.entrytable.set_sensitive(False)
        scanname = 'scan_' + str(self.scan.fsn)
        fileformat = 'scan_%05d.cbf'
        self.progress.show_all()
        self.get_widget_for_response(Gtk.ResponseType.OK).set_sensitive(False)
        kwargs_for_plot2d = {'qrange_on_axis':False, 'drawmask':False, 'crosshair':False}
        if self.Imax_checkbutton.get_active():
            kwargs_for_plot2d['maxvalue'] = self.Imax_entry.get_value()
        if self.Imin_checkbutton.get_active():
            kwargs_for_plot2d['minvalue'] = self.Imin_entry.get_value()
        kwargs_for_plot2d['zscale'] = self.colourscale_combo.get_active_text()
        if self.pri_checkbutton.get_active():
            axis = (self.prileft_entry.get_value(), self.priright_entry.get_value(), self.pribottom_entry.get_value(), self.pritop_entry.get_value())
        else:
            axis = None
        for i in [int(fsn) for fsn in self.scan['FSN']]:
            ex = sastool.classes.SASExposure(fileformat % i, dirs=self.credo.subsystems['Files'].rawloadpath)
            fig.clf()
            ex.plot2d(**kwargs_for_plot2d)
            if axis is not None:
                plt.gca().axis(axis)
            fig.gca().set_title(scanname)
            fig.text(1, 0, '%s@CREDO %s' % (ex['Owner'], str(ex['Date'])), ha='right', va='bottom')
            if not os.path.isdir(os.path.join(self.credo.moviepath, scanname)):
                os.mkdir(os.path.join(self.credo.moviepath, scanname))
            fig.savefig(os.path.join(self.credo.moviepath, scanname, (fileformat % i).replace('.cbf', '.png')))
            del ex
            self.pulse(float(i) / len(self.scan))
            if self._userbreak:
                break
        # fig.close()
        del fig
        if (i < len(self.scan)):
            return False
        moviefilespresent = [f for f in os.listdir(self.credo.moviepath) if f.startswith(scanname) and f.endswith('.avi')]
        if not moviefilespresent:
            outname = scanname + '.avi'
        else:
            try:
                outname = scanname + 'm%03d.avi' % (max([int(m.group(1)) for m in 
                                                         [m for m in 
                                                          [re.match(scanname + 'm(?P<num>\d+).avi', f) 
                                                           for f in moviefilespresent ] if m is not None]]) + 1)
            except ValueError:
                outname = scanname + 'm001.avi'
        cwd = os.getcwd()
        def _encoder_thread():
            os.chdir(os.path.join(self.credo.moviepath, scanname))
            os.system('mencoder mf://*.png -mf w=800:h=600:fps=%d:type=png -ovc lavc -lavcopts vcodec=mpeg4:mbd=2:trell -oac copy -o ../%s' % (self.fps_entry.get_value_as_int(), outname))
            os.chdir(cwd)
        encthread = threading.Thread(name='Encoding_movie', target=_encoder_thread)
        encthread.setDaemon(True)
        encthread.start()
        _pulser = GLib.timeout_add(100, self.pulse)
        while encthread.isAlive():
            while Gtk.events_pending():
                Gtk.main_iteration()
        GLib.source_remove(_pulser)
        shutil.rmtree(os.path.join(self.credo.moviepath, scanname))
        self.get_widget_for_response(Gtk.ResponseType.OK).set_sensitive(True)
        self.pri_frame.set_sensitive(True)
        self.entrytable.set_sensitive(True)
        self.progress.hide()
        md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, 'Movie file %s is ready.' % os.path.join(self.credo.moviepath, outname))
        md.run()
        md.destroy()
        return False
    def pulse(self, frac=None):
        if frac is None:
            self.progress.set_text('Converting .png files to .avi...')
            self.progress.pulse()
        else:
            self.progress.set_text('Making .png files...')
            self.progress.set_fraction(frac)
        while Gtk.events_pending():
            Gtk.main_iteration()
        return True
