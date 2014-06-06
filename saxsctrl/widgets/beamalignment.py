import collections
from gi.repository import Gtk
import sasgui
import numpy as np
import gc
import logging
import sastool
from .widgets import ToolDialog
from .exposure import ExposureFrame

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class BeamAlignment(ToolDialog):
    _images_pending = []
    def __init__(self, credo, title='Beam alignment'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))

        vb = self.get_content_area()
        tab = Gtk.Table()
        self.entrytable = tab
        vb.pack_start(tab, False, True, 0)
        row = 0
        
        l = Gtk.Label(label='Comment:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.comment_entry = Gtk.Entry()
        self.comment_entry.set_text('-- please fill --')
        tab.attach(self.comment_entry, 1, 2, row, row + 1)
        row += 1

        self.exposure_frame = ExposureFrame(self.credo, 'tst')
        tab.attach(self.exposure_frame, 0, 2, row, row + 1)
        self.exposure_frame.connect('started', self._on_start)
        self.exposure_frame.connect('end', self._on_end)
        self.exposure_frame.connect('image', self._on_image)
        row += 1

        self.plot_checkbutton = Gtk.CheckButton('Plot after exposure')
        self.plot_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.plot_checkbutton, 0, 2, row, row + 1)
        self.plot_checkbutton.set_active(True)
        row += 1

        self.reuse_checkbutton = Gtk.CheckButton('Re-use plot')
        self.reuse_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.reuse_checkbutton, 0, 2, row, row + 1)
        self.reuse_checkbutton.set_active(True)
        row += 1

        
        self.beamposframe = Gtk.Frame(label='Beam position finding')
        vb.pack_start(self.beamposframe, False, True, 0)
        tab = Gtk.Table()
        self.beamposframe.add(tab)
        row = 0
        
        l = Gtk.Label(label=u'Beam area top:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.pri_top_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -10000, 10000, 0.1, 1), digits=2)
        tab.attach(self.pri_top_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label=u'Beam area bottom:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.pri_bottom_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -10000, 10000, 0.1, 1), digits=2)
        tab.attach(self.pri_bottom_entry, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label=u'Beam area left:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.pri_left_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -10000, 10000, 0.1, 1), digits=2)
        tab.attach(self.pri_left_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label=u'Beam area right:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.pri_right_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -10000, 10000, 0.1, 1), digits=2)
        tab.attach(self.pri_right_entry, 1, 2, row, row + 1)
        row += 1

        b = Gtk.Button('Set\nfrom\ncurrent\nzoom')
        tab.attach(b, 2, 3, 0, row, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b.connect('clicked', self.on_set_limits_from_zoom)


        self.threshold_checkbutton = Gtk.CheckButton(u'Relative intensity threshold:')
        self.threshold_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.threshold_checkbutton, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.threshold_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0.05, 0, 1, 0.1, 1), digits=2)
        tab.attach(self.threshold_entry, 1, 2, row, row + 1)
        self.threshold_checkbutton.connect('toggled', self.on_threshold_toggled, self.threshold_entry)
        self.on_threshold_toggled(self.threshold_checkbutton, self.threshold_entry)
        row += 1
        
        f = Gtk.Frame(label='Found position:')
        vb.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        l = Gtk.Label(label='Mean value')
        tab.attach(l, 1, 2, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label(label='Std. value')
        tab.attach(l, 2, 3, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label(label='# of data')
        tab.attach(l, 3, 4, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.resultlabels = collections.OrderedDict()
        for row, name in enumerate(['X Pos', 'Y Pos', 'X RMS', 'Y RMS', 'Total RMS', 'Max intensity', 'Mean intensity', 'RMS intensity', 'Total intensity']):
            thislabel = {}
            l = Gtk.Label(label=name); l.set_alignment(0, 0.5)
            tab.attach(l, 0, 1, row + 1, row + 2, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
            for col, what in enumerate(['mean', 'rms', 'num']):
                thislabel[what] = Gtk.Label(label='--'); thislabel[what].set_alignment(0, 0.5)
                tab.attach(thislabel[what], col + 1, col + 2, row + 1, row + 2, xpadding=3)
            self.resultlabels[name] = thislabel
        vb.show_all()
    def on_threshold_toggled(self, cb, entry):
        entry.set_sensitive(cb.get_active())
    def on_set_limits_from_zoom(self, widget):
        ax = sasgui.PlotSASImageWindow.get_current_plot().get_zoom()
        for sb, val in zip([self.pri_left_entry, self.pri_right_entry, self.pri_bottom_entry, self.pri_top_entry], ax):
            sb.set_value(val)
    def _on_start(self, expframe):
        for w in [self.beamposframe, self.entrytable, self.get_widget_for_response(Gtk.ResponseType.CLOSE)]:
            w.set_sensitive(False)
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_STOP)
        
    def do_response(self, respid):
        if respid == Gtk.ResponseType.OK:
            if self.beamposframe.get_sensitive():
                self.credo.subsystems['Samples'].set(None)
                self._images_pending = []
                self.exposure_frame.execute({'Comment':self.comment_entry.get_text()}, write_nexus=False)
            else:
                self.exposure_frame.kill()
        else:
            self.destroy()
        return True
    def get_beamarea(self):
        return (self.pri_top_entry.get_value(), self.pri_bottom_entry.get_value(), self.pri_left_entry.get_value(), self.pri_right_entry.get_value()) 
    def _on_end(self, expframe, status):
        for w in [self.beamposframe, self.entrytable, self.get_widget_for_response(Gtk.ResponseType.CLOSE)]:
            w.set_sensitive(True)
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_EXECUTE)
        logger.debug('last image received, analyzing images.')
        pri = self.get_beamarea()
        
        if self.threshold_checkbutton.get_active():
            threshold = self.threshold_entry.get_value()
        else:
            threshold = None
        beampos = []
        if (pri[0] - pri[1]) * (pri[2] - pri[3]) != 0:
            mask1 = sastool.classes.SASMask(self._images_pending[0].shape)
            mask1.edit_rectangle(pri[0], pri[2], pri[1], pri[3], whattodo='unmask')
        for ex in self._images_pending:
            if (pri[0] - pri[1]) * (pri[2] - pri[3]) != 0:
                ex.mask &= mask1
            try:
                if threshold is not None:
                    beampos.append(ex.find_beam_semitransparent(pri, threshold))
                else:
                    beampos.append(ex.barycenter())
            except Exception, err:
                logger.error('Beam finding error: ' + str(err))
        bcx = [b[0] for b in beampos]
        bcy = [b[1] for b in beampos]
        Imax = [ex.max() for ex in self._images_pending]
        Isum = [ex.sum() for ex in self._images_pending]
        Imean = [ex.mean() for ex in self._images_pending]
        Istd = [ex.std() for ex in self._images_pending]
        sigma = [ex.sigma() for ex in self._images_pending]
        sigmax = [s[0] for s in sigma]
        sigmay = [s[1] for s in sigma]
        sigmatot = [(s[0] ** 2 + s[1] ** 2) ** 0.5 for s in sigma]
        for name, entity in [('X Pos', bcx), ('Y Pos', bcy), ('X RMS', sigmax), ('Y RMS', sigmay), ('Total RMS', sigmatot), ('Max intensity', Imax),
                            ('Mean intensity', Imean), ('RMS intensity', Istd), ('Total intensity', Isum)]:
            self.resultlabels[name]['mean'].set_text(str(np.mean(entity)))
            self.resultlabels[name]['rms'].set_text(str(np.std(entity)))
            self.resultlabels[name]['num'].set_text(str(len(entity)))
        logger.debug('BeamX: %f; BeamY: %f; Imax: %f; Isum: %f; Imean: %f; Istd: %f' % (np.mean(bcx), np.mean(bcy), np.mean(Imax), np.mean(Isum), np.mean(Imean), np.mean(Istd)))
        self._images_pending = []
        gc.collect()
            
    def _on_image(self, expframe, imgdata):
        pri = (self.pri_top_entry.get_value(),
               self.pri_bottom_entry.get_value(),
               self.pri_left_entry.get_value(),
               self.pri_right_entry.get_value())
        logger.debug('image received.')
        self._images_pending.append(imgdata)
        if self.plot_checkbutton.get_active():
            logger.debug('plotting received image')
            if self.reuse_checkbutton.get_active():
                win = sasgui.plot2dsasimage.PlotSASImageWindow.get_current_plot()
                win.set_exposure(imgdata)
                win.show_all()
                win.present()
            else:
                win = sasgui.plot2dsasimage.PlotSASImageWindow(imgdata)
                win.show_all()
            if not ((pri[0] == pri[1]) and (pri[2] == pri[3])):
                win.plot.zoom((pri[2], pri[3], pri[1], pri[0]))
        return False
    
