# coding: utf-8
from gi.repository import Gtk
from gi.repository import GLib
import logging
import sastool
from .spec_filechoosers import MaskChooserDialog
from .nextfsn_monitor import NextFSNMonitor
from .samplesetup import SampleSelector
import multiprocessing
from .widgets import ToolDialog
from .exposure import ExposureFrame

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
from gi.repository import GObject
import sasgui
import datetime
import os
from .data_reduction_setup import PleaseWaitInfoBar
import qrcode

class SingleExposure(ToolDialog):
    _filechooserdialogs = None
    def __init__(self, credo, title='Single exposure'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        self.set_default_response(Gtk.ResponseType.OK)
        vb = self.get_content_area()
        
        self.entrytab = Gtk.Table()
        vb.pack_start(self.entrytab, False, True, 0)
        self.set_resizable(False)
        row = 0
        
        l = Gtk.Label(label='Sample:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.sample_combo = SampleSelector(self.credo)
        self.entrytab.attach(self.sample_combo, 1, 2, row, row + 1)
        row += 1
        
        self.expframe = ExposureFrame(self.credo)
        self.entrytab.attach(self.expframe, 0, 2, row, row + 1)
        self._conns = [self.expframe.connect('started', self._on_start),
                     self.expframe.connect('end', self._on_end),
                     self.expframe.connect('image', self._on_image),
                     ]
        row += 1
        
        self.datareduction_cb = Gtk.CheckButton('Carry out data reduction'); self.datareduction_cb.set_alignment(0, 0.5)
        self.entrytab.attach(self.datareduction_cb, 0, 2, row, row + 1)
        row += 1
        
        f = Gtk.Frame(label='2D plot')
        vb.pack_start(f, False, True, 0)
        
        vb1 = Gtk.VBox()
        f.add(vb1)
        self.plot2D_checkbutton = Gtk.CheckButton('Plot image afterwards'); self.plot2D_checkbutton.set_alignment(0, 0.5)
        vb1.pack_start(self.plot2D_checkbutton, True, True, 0)
        self.plot2D_checkbutton.set_active(True)
        self.reuse2D_checkbutton = Gtk.CheckButton('Re-use plot window'); self.reuse2D_checkbutton.set_alignment(0, 0.5)
        vb1.pack_start(self.reuse2D_checkbutton, True, True, 0)
        self.reuse2D_checkbutton.set_active(True)

        f = Gtk.Frame(label='1D plot')
        vb.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        
        self.plot1D_checkbutton = Gtk.CheckButton('Plot curve afterwards'); self.plot1D_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.plot1D_checkbutton, 0, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        self.plot1D_checkbutton.set_active(True)
        self.reuse1D_checkbutton = Gtk.CheckButton('Re-use plot window'); self.reuse1D_checkbutton.set_alignment(0, 0.5)
        self.reuse1D_checkbutton.set_active(True)
        tab.attach(self.reuse1D_checkbutton, 0, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        
        self.q_or_pixel_checkbutton = Gtk.CheckButton('Q on abscissa'); self.q_or_pixel_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.q_or_pixel_checkbutton, 0, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        
        l = Gtk.Label(label='Plot method:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.plot1d_method = Gtk.ComboBoxText()
        tab.attach(self.plot1d_method, 1, 2, row, row + 1)
        self.plot1d_method.append_text('plot')
        self.plot1d_method.append_text('semilogx')
        self.plot1d_method.append_text('semilogy')
        self.plot1d_method.append_text('loglog')
        self.plot1d_method.set_active(3)
        
        vb.pack_start(NextFSNMonitor(self.credo, 'Next exposure'), True, True, 0)
        
        self._datareduction = []
        self._expsleft = 0
    def do_destroy(self):
        if hasattr(self, '_conns'):
            for c in self._conns:
                self.expframe.disconnect(c)
            del self._conns

    def do_response(self, respid):
        if respid == Gtk.ResponseType.OK:
            if self.get_widget_for_response(Gtk.ResponseType.OK).get_label() == Gtk.STOCK_EXECUTE:
                sam = self.sample_combo.get_sample()
                logger.info('Starting single exposure on sample: ' + str(sam))
                self.credo.subsystems['Samples'].set(sam)
                self.credo.subsystems['Samples'].moveto(blocking=True)
                # make an exposure
                self.expframe.execute()
            else:
                # break the exposure
                self.expframe.kill()
        elif respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            logger.debug('Destroying a SingleExposure Window.')
            self.destroy()
            logger.debug('Destroying of a SingleExposure window ended.')
    def on_datareduction_done(self, datareduction, jobidx, exposure):
        if not hasattr(self, '_datared_connection'):
            return False
        if jobidx not in self._datareduction:
            return False
        exposure.write(os.path.join(self.credo.eval2dpath, 'crd_%05d.h5' % exposure['FSN']))
        exposure.radial_average().save(os.path.join(self.credo.eval1dpath, 'crd_%05d.txt' % exposure['FSN']))
        self._datareduction.remove(jobidx)
        self.datared_infobar.set_n_jobs(len(self._datareduction))
        if not self._datareduction:  # no more running jobs
            for c in self._datared_connection:
                self.credo.datareduction.disconnect(c)
            self.datared_infobar.destroy()
            del self.datared_infobar
        GLib.idle_add(self.plot_image, exposure)
        return True
    def on_datareduction_message(self, datareduction, jobidx, message):
        if not hasattr(self, '_datareduction'):
            return False
        if jobidx not in self._datareduction:
            return False
        self.datared_infobar.set_label_text(message)
        return True
    def _on_start(self, expframe):
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_STOP)
        for w in [self.entrytab]:
            w.set_sensitive(False)
        pass
    def _on_end(self, expframe, state):
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_EXECUTE)
        for w in [self.entrytab]:
            w.set_sensitive(True)
    def _on_image(self, expframe, exposure):
        logger.debug('Image received.')
        if self.datareduction_cb.get_active():
            if not hasattr(self, 'datared_infobar'):
                self.datared_infobar = PleaseWaitInfoBar()
                self.get_content_area().pack_start(self.datared_infobar, False, False, 0)
                self.get_content_area().reorder_child(self.datared_infobar, 0)
                self.datared_infobar.show_all()
                self._datared_connection = [self.credo.datareduction.connect('done', self.on_datareduction_done),
                                            self.credo.datareduction.connect('message', self.on_datareduction_message)]
            self._datareduction.append(self.credo.datareduction.do_reduction(exposure))
            self.datared_infobar.set_n_jobs(len(self._datareduction))
        else:
            GLib.idle_add(self.plot_image, exposure)
        
    def plot_image(self, exposure):
        logger.debug('Plotting image.')
        if self.plot2D_checkbutton.get_active():
            if self.reuse2D_checkbutton.get_active():
                win = sasgui.plot2dsasimage.PlotSASImageWindow.get_current_plot()
            else:
                win = sasgui.plot2dsasimage.PlotSASImageWindow()
            win.set_exposure(exposure)
            win.set_bottomrightdata(self.credo.username + '@CREDO ' + str(exposure['Date']))
            win.set_bottomleftdata(qrcode.make(self.credo.username + '@CREDO://' + str(exposure.header) + ' ' + str(exposure['Date']), box_size=10))
            win.show_all()
            win.present()
        if self.plot1D_checkbutton.get_active():
            rad = exposure.radial_average(pixel=not self.q_or_pixel_checkbutton.get_active())
            if self.reuse2D_checkbutton.get_active():
                win = sasgui.plot1dsascurve.PlotSASCurveWindow.get_current_plot()
            else:
                win = sasgui.plot1dsascurve.PlotSASCurveWindow()
            func = win.__getattribute__(self.plot1d_method.get_active_text())
            func(rad, label=str(exposure.header))
            win.legend(loc='best')
            if self.q_or_pixel_checkbutton.get_active():
                win.xlabel(u'q (1/\xc5)')
            else:
                win.xlabel(u'Radial pixel number')
            win.ylabel('Intensity (total counts)')
            win.show_all()
            win.present()
        return False
