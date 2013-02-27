import gtk
import os
import matplotlib.pyplot as plt
import shutil
import gobject
from ..fileformats.scan import Scan
import sastool
import threading
import re


class MovieMaker(gtk.Dialog):
    def __init__(self, credo, scanname, title='Create movie from scan', parent=None, flags=0, buttons=(gtk.STOCK_EXECUTE, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_CANCEL)
        self.credo = credo
        self.scanname = scanname
        vb = self.get_content_area()
        self.pritable = gtk.Table()
        
        self.pri_frame = gtk.Frame('Image boundary')
        vb.pack_start(self.pri_frame, False)
        vb1 = gtk.VBox()
        self.pri_frame.add(vb1)
        self.pri_checkbutton = gtk.CheckButton('Respect boundary')
        vb1.pack_start(self.pri_checkbutton)
        self.pri_checkbutton.connect('toggled', self.on_sensitivity_checkbutton, self.pritable)
        self.on_sensitivity_checkbutton(self.pri_checkbutton, self.pritable)
        vb1.pack_start(self.pritable, False)
        row = 0
        
        l = gtk.Label('Top:'); l.set_alignment(0, 0.5)
        self.pritable.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.pritop_entry = gtk.SpinButton(gtk.Adjustment(0, -1e10, 1e10, 1, 10), digits=2)
        self.pritable.attach(self.pritop_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Bottom:'); l.set_alignment(0, 0.5)
        self.pritable.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.pribottom_entry = gtk.SpinButton(gtk.Adjustment(0, -1e10, 1e10, 1, 10), digits=2)
        self.pritable.attach(self.pribottom_entry, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Left:'); l.set_alignment(0, 0.5)
        self.pritable.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.prileft_entry = gtk.SpinButton(gtk.Adjustment(0, -1e10, 1e10, 1, 10), digits=2)
        self.pritable.attach(self.prileft_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Right:'); l.set_alignment(0, 0.5)
        self.pritable.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.priright_entry = gtk.SpinButton(gtk.Adjustment(0, -1e10, 1e10, 1, 10), digits=2)
        self.pritable.attach(self.priright_entry, 1, 2, row, row + 1)
        row += 1

        self.entrytable = gtk.Table()
        vb.pack_start(self.entrytable, False)
        row = 0

        self.Imin_checkbutton = gtk.CheckButton('Lower intensity cut-off:'); self.Imin_checkbutton.set_alignment(0, 0.5)
        self.entrytable.attach(self.Imin_checkbutton, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.Imin_entry = gtk.SpinButton(gtk.Adjustment(0, 0, 1e100, 1, 10), digits=0)
        self.entrytable.attach(self.Imin_entry, 1, 2, row, row + 1)
        self.Imin_checkbutton.connect('toggled', self.on_sensitivity_checkbutton, self.Imin_entry)
        self.on_sensitivity_checkbutton(self.Imin_checkbutton, self.Imin_entry)
        row += 1
        
        self.Imax_checkbutton = gtk.CheckButton('Upper intensity cut-off:'); self.Imax_checkbutton.set_alignment(0, 0.5)
        self.entrytable.attach(self.Imax_checkbutton, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.Imax_entry = gtk.SpinButton(gtk.Adjustment(0, 0, 1e100, 1, 10), digits=0)
        self.entrytable.attach(self.Imax_entry, 1, 2, row, row + 1)
        self.Imax_checkbutton.connect('toggled', self.on_sensitivity_checkbutton, self.Imax_entry)
        self.on_sensitivity_checkbutton(self.Imax_checkbutton, self.Imax_entry)
        row += 1

        l = gtk.Label('Colour scaling:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.colourscale_combo = gtk.combo_box_new_text()
        for l in ['linear', 'log', 'sqrt']:
            self.colourscale_combo.append_text(l)
        self.colourscale_combo.set_active(0)
        self.entrytable.attach(self.colourscale_combo, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Movie fps:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.fps_entry = gtk.SpinButton(gtk.Adjustment(25, 0, 100, 1, 10), digits=0)
        self.entrytable.attach(self.fps_entry, 1, 2, row, row + 1)
        vb.show_all()
        
        self.progress = gtk.ProgressBar()
        # self.get_action_area().pack_start(self.progress, False)
        vb.pack_start(self.progress, False)

        self.connect('response', self.on_response)
        self._userbreak = False
    def on_sensitivity_checkbutton(self, checkbutton, widget):
        widget.set_sensitive(checkbutton.get_active())
    def on_response(self, dialog, respid):
        if respid == gtk.RESPONSE_CANCEL:
            self._userbreak = True
            return
        elif respid == gtk.RESPONSE_DELETE_EVENT:
            return
        else:
            self.on_run()
            return
    def on_run(self):
        scan = Scan(os.path.join(self.credo.scanpath, self.scanname) + '.txt')
        fig = plt.figure()
        self.pri_frame.set_sensitive(False)
        self.entrytable.set_sensitive(False)
        fileformat = self.scanname + '_%05d.cbf'
        self.progress.show_all()
        self.get_widget_for_response(gtk.RESPONSE_OK).set_sensitive(False)
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
        for i in range(1, len(scan) + 1):
            ex = sastool.classes.SASExposure(fileformat % i, dirs=self.credo.get_exploaddirs())
            fig.clf()
            ex.plot2d(**kwargs_for_plot2d)
            if axis is not None:
                plt.gca().axis(axis)
            fig.gca().set_title(self.scanname)
            fig.text(1, 0, '%s@CREDO %s' % (ex['Owner'], str(ex['Date'])), ha='right', va='bottom')
            if not os.path.isdir(os.path.join(self.credo.moviepath, self.scanname)):
                os.mkdir(os.path.join(self.credo.moviepath, self.scanname))
            fig.savefig(os.path.join(self.credo.moviepath, self.scanname, (fileformat % i).replace('.cbf', '.png')))
            del ex
            self.pulse(float(i) / len(scan))
            if self._userbreak:
                break
        # fig.close()
        del fig
        if (i < len(scan)):
            return False
        filespresent = [f for f in os.listdir(self.credo.moviepath) if f.startswith(self.scanname) and f.endswith('.avi')]
        if not filespresent:
            outname = self.scanname + '.avi'
        else:
            try:
                outname = self.scanname + 'm%03d.avi' % (max([int(m.group(1)) for m in [m for m in [re.match(self.scanname + 'm(?P<num>\d+).avi', f) for f in filespresent ] if m is not None]]) + 1)
            except ValueError:
                outname = self.scanname + 'm001.avi'
        cwd = os.getcwd()
        def _encoder_thread():
            os.chdir(os.path.join(self.credo.moviepath, self.scanname))
            os.system('mencoder mf://*.png -mf w=800:h=600:fps=%d:type=png -ovc lavc -lavcopts vcodec=mpeg4:mbd=2:trell -oac copy -o ../%s' % (self.fps_entry.get_value_as_int(), outname))
            os.chdir(cwd)
        encthread = threading.Thread(name='Encoding_movie', target=_encoder_thread)
        encthread.setDaemon(True)
        encthread.start()
        _pulser = gobject.timeout_add(100, self.pulse)
        while encthread.isAlive():
            while gtk.events_pending():
                gtk.main_iteration()
        gobject.source_remove(_pulser)
        shutil.rmtree(os.path.join(self.credo.moviepath, self.scanname))
        self.get_widget_for_response(gtk.RESPONSE_OK).set_sensitive(True)
        self.pri_frame.set_sensitive(True)
        self.entrytable.set_sensitive(True)
        self.progress.hide()
        md = gtk.MessageDialog(self, gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL, gtk.MESSAGE_INFO, gtk.BUTTONS_OK, 'Movie file %s is ready.' % os.path.join(self.credo.moviepath, outname))
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
        # print "PULSE"
        while gtk.events_pending():
            gtk.main_iteration()
        return True
