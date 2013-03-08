# coding: utf-8
from gi.repository import Gtk
import logging
import sastool
from .spec_filechoosers import MaskChooserDialog
from .nextfsn_monitor import NextFSNMonitor
logger = logging.getLogger('singleexposure')
from gi.repository import GObject
import sasgui
import datetime

class SingleExposure(Gtk.Dialog):
    _filechooserdialogs = None
    def __init__(self, credo, title='Single exposure', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        self.credo = credo
        vb = self.get_content_area()
        self.entrytab = Gtk.Table()
        vb.pack_start(self.entrytab, False, True, 0)
        self.set_resizable(False)
        row = 0
        
        l = Gtk.Label(label='Sample:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.sample_combo = Gtk.ComboBoxText()
        self.entrytab.attach(self.sample_combo, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Exposure time:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(60, 0.0001, 1e10, 1, 10), digits=4)
        self.entrytab.attach(self.exptime_entry, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Mask:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        hb = Gtk.HBox()
        self.maskfile_entry = Gtk.Entry()
        hb.pack_start(self.maskfile_entry, True, True, 0)
        b = Gtk.Button(stock=Gtk.STOCK_OPEN)
        hb.pack_start(b, False, True, 0)
        b.connect('clicked', self.on_loadmaskbutton, self.maskfile_entry, Gtk.FileChooserAction.OPEN)
        self.entrytab.attach(hb, 1, 2, row, row + 1)
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
        self.reuse2D_checkbutton = Gtk.CheckButton('Re-use plot window'); self.reuse2D_checkbutton.set_alignment(0, 0.5)
        vb1.pack_start(self.reuse2D_checkbutton, True, True, 0)

        f = Gtk.Frame(label='1D plot')
        vb.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        
        self.plot1D_checkbutton = Gtk.CheckButton('Plot curve afterwards'); self.plot1D_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.plot1D_checkbutton, 0, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        
        self.reuse1D_checkbutton = Gtk.CheckButton('Re-use plot window'); self.reuse1D_checkbutton.set_alignment(0, 0.5)
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
        
        self.credo.connect_callback('samples-changed', self.reload_samples)
        self.reload_samples()
        self.connect('response', self.on_response)
    def reload_samples(self, *args):
        self.sample_combo.get_model().clear()
        idx = 0
        for i, sam in enumerate(self.credo.get_samples()):
            if sam == self.credo.sample:
                idx = i
            self.sample_combo.append_text(u'%s (%.2f°C @%.2f)' % (sam.title, sam.temperature, sam.position))
        self.sample_combo.set_active(idx)
            
    def on_loadmaskbutton(self, button, entry, action):
        if self._filechooserdialogs is None:
            self._filechooserdialogs = {}
        if entry not in self._filechooserdialogs:
            
            self._filechooserdialogs[entry] = MaskChooserDialog('Select mask file...', None, action, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
            if self.credo is not None:
                self._filechooserdialogs[entry].set_current_folder(self.credo.maskpath)
        if entry.get_text():
            self._filechooserdialogs[entry].set_filename(entry.get_text())
        response = self._filechooserdialogs[entry].run()
        if response == Gtk.ResponseType.OK:
            entry.set_text(self._filechooserdialogs[entry].get_filename())
        self._filechooserdialogs[entry].hide()
        return True
    def on_response(self, dialog, respid):
        if respid == Gtk.ResponseType.OK:
            if self.get_widget_for_response(Gtk.ResponseType.OK).get_label() == Gtk.STOCK_EXECUTE:
                sam = self.credo.get_samples()[self.sample_combo.get_active()]
                logger.info('Starting single exposure on sample: ' + str(sam))
                # make an exposure
                self.entrytab.set_sensitive(False)
                self.get_widget_for_response(Gtk.ResponseType.CLOSE).set_sensitive(False)
                sam = self.credo.get_samples()[self.sample_combo.get_active()]
                self.credo.set_sample(sam)
                self.credo.set_fileformat('crd', 5)
                def _handler(imgdata):
                    GObject.idle_add(self.on_imagereceived, imgdata)
                    return False
                logger.debug('Calling credo.expose')
                header_template = {'maskid':self.maskfile_entry.get_text()}
                if isinstance(sam.thickness, sastool.misc.errorvalue.ErrorValue):
                    header_template['ThicknessError'] = sam.thickness.err
                
                self.credo.expose(self.exptime_entry.get_value(), blocking=False, callback=_handler, header_template=header_template)
                self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_STOP)
            else:
                # break the exposure
                self.credo.killexposure()
                self.on_imagereceived(None)
        elif respid == Gtk.ResponseType.CLOSE:
            self.hide()
            return
    def on_imagereceived(self, exposure):
        if exposure is not None:
            mask = sastool.classes.SASMask(self.maskfile_entry.get_text())
            exposure.set_mask(mask)
            if self.datareduction_cb.get_active():
                exposure = self.credo.datareduction.do_reduction(exposure)
            if self.plot2D_checkbutton.get_active():
                logger.debug('plotting received image')
                if self.reuse2D_checkbutton.get_active():
                    win = sasgui.plot2dsasimage.PlotSASImageWindow.get_current_plot()
                    win.set_exposure(exposure)
                    win.show_all()
                    win.present()
                else:
                    def cbfunc(ex, fig, ax):
                        ax.set_title(str(ex.header))
                        fig.text(1, 0, self.credo.username + '@CREDO' + str(datetime.datetime.now()), ha='right', va='bottom')
                    win = sasgui.plot2dsasimage.PlotSASImageWindow(exposure, cbfunc)
                    win.show_all()
            if self.plot1D_checkbutton.get_active():
                if self.q_or_pixel_checkbutton.get_active():
                    rad = exposure.radial_average()
                else:
                    rad = exposure.radial_average(pixel=True)
                if self.reuse2D_checkbutton.get_active():
                    win = sasgui.plot1dsascurve.PlotSASCurveWindow.get_current_plot()
                else:
                    win = sasgui.plot1dsascurve.PlotSASCurveWindow()
                func = win.__getattribute__(self.plot1d_method.get_active_text())
                func(rad, label=str(exposure.header))
                win.legend(loc='best')
                win.show_all()
                win.present()
        self.entrytab.set_sensitive(True)
        self.get_widget_for_response(Gtk.ResponseType.CLOSE).set_sensitive(True)
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_EXECUTE)
        return False   
            
