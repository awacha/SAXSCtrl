
# coding: utf-8
import gtk
import logging
import sastool
from .spec_filechoosers import MaskChooserDialog
from .nextfsn_monitor import NextFSNMonitor
logger = logging.getLogger('singleexposure')
import gobject
import sasgui

class SingleExposure(gtk.Dialog):
    _filechooserdialogs = None
    def __init__(self, credo, title='Single exposure', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_EXECUTE, gtk.RESPONSE_OK, gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.credo = credo
        vb = self.get_content_area()
        self.entrytab = gtk.Table()
        vb.pack_start(self.entrytab, False)
        self.set_resizable(False)
        row = 0
        
        l = gtk.Label('Sample:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.sample_combo = gtk.combo_box_new_text()
        self.entrytab.attach(self.sample_combo, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Exposure time:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.exptime_entry = gtk.SpinButton(gtk.Adjustment(60, 0.0001, 1e10, 1, 10), digits=4)
        self.entrytab.attach(self.exptime_entry, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Mask:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        hb = gtk.HBox()
        self.maskfile_entry = gtk.Entry()
        hb.pack_start(self.maskfile_entry)
        b = gtk.Button(stock=gtk.STOCK_OPEN)
        hb.pack_start(b, False)
        b.connect('clicked', self.on_loadmaskbutton, self.maskfile_entry, gtk.FILE_CHOOSER_ACTION_OPEN)
        self.entrytab.attach(hb, 1, 2, row, row + 1)
        row += 1
        
        f = gtk.Frame('2D plot')
        vb.pack_start(f, False)
        
        vb1 = gtk.VBox()
        f.add(vb1)
        self.plot2D_checkbutton = gtk.CheckButton('Plot image afterwards'); self.plot2D_checkbutton.set_alignment(0, 0.5)
        vb1.pack_start(self.plot2D_checkbutton)
        self.reuse2D_checkbutton = gtk.CheckButton('Re-use plot window'); self.reuse2D_checkbutton.set_alignment(0, 0.5)
        vb1.pack_start(self.reuse2D_checkbutton)

        f = gtk.Frame('1D plot')
        vb.pack_start(f, False)
        tab = gtk.Table()
        f.add(tab)
        row = 0
        
        self.plot1D_checkbutton = gtk.CheckButton('Plot curve afterwards'); self.plot1D_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.plot1D_checkbutton, 0, 2, row, row + 1, gtk.FILL, gtk.FILL)
        row += 1
        
        self.reuse1D_checkbutton = gtk.CheckButton('Re-use plot window'); self.reuse1D_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.reuse1D_checkbutton, 0, 2, row, row + 1, gtk.FILL, gtk.FILL)
        row += 1
        
        self.q_or_pixel_checkbutton = gtk.CheckButton('Q on abscissa'); self.q_or_pixel_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.q_or_pixel_checkbutton, 0, 2, row, row + 1, gtk.FILL, gtk.FILL)
        row += 1
        
        l = gtk.Label('Plot method:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.plot1d_method = gtk.combo_box_new_text()
        tab.attach(self.plot1d_method, 1, 2, row, row + 1)
        self.plot1d_method.append_text('plot')
        self.plot1d_method.append_text('semilogx')
        self.plot1d_method.append_text('semilogy')
        self.plot1d_method.append_text('loglog')
        self.plot1d_method.set_active(3)
        
        vb.pack_start(NextFSNMonitor(self.credo, 'Next exposure'))
        
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
            
            self._filechooserdialogs[entry] = MaskChooserDialog('Select mask file...', None, action, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
            if self.credo is not None:
                self._filechooserdialogs[entry].set_current_folder(self.credo.maskpath)
        if entry.get_text():
            self._filechooserdialogs[entry].set_filename(entry.get_text())
        response = self._filechooserdialogs[entry].run()
        if response == gtk.RESPONSE_OK:
            entry.set_text(self._filechooserdialogs[entry].get_filename())
        self._filechooserdialogs[entry].hide()
        return True
    def on_response(self, dialog, respid):
        if respid == gtk.RESPONSE_OK:
            if self.get_widget_for_response(gtk.RESPONSE_OK).get_label() == gtk.STOCK_EXECUTE:
                sam = self.credo.get_samples()[self.sample_combo.get_active()]
                logger.info('Starting single exposure on sample: ' + str(sam))
                # make an exposure
                self.entrytab.set_sensitive(False)
                self.get_widget_for_response(gtk.RESPONSE_CLOSE).set_sensitive(False)
                sam = self.credo.get_samples()[self.sample_combo.get_active()]
                self.credo.set_sample(sam)
                self.credo.set_fileformat('crd', 5)
                def _handler(imgdata):
                    gobject.idle_add(self.on_imagereceived, imgdata)
                    return False
                logger.debug('Calling credo.expose')
                self.credo.expose(self.exptime_entry.get_value(), blocking=False, callback=_handler)
                self.get_widget_for_response(gtk.RESPONSE_OK).set_label(gtk.STOCK_STOP)
            else:
                # break the exposure
                self.credo.killexposure()
                self.on_imagereceived(None)
        elif respid == gtk.RESPONSE_CLOSE:
            self.hide()
            return
    def on_imagereceived(self, exposure):
        if exposure is not None:
            mask = sastool.classes.SASMask(self.maskfile_entry.get_text())
            exposure.set_mask(mask)
            if self.plot2D_checkbutton.get_active():
                logger.debug('plotting received image')
                if self.reuse2D_checkbutton.get_active():
                    win = sasgui.plot2dsasimage.PlotSASImageWindow.get_current_plot()
                    win.set_exposure(exposure)
                    win.show_all()
                    win.present()
                else:
                    win = sasgui.plot2dsasimage.PlotSASImageWindow(exposure)
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
        self.get_widget_for_response(gtk.RESPONSE_CLOSE).set_sensitive(True)
        self.get_widget_for_response(gtk.RESPONSE_OK).set_label(gtk.STOCK_EXECUTE)
        return False   
            
