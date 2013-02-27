import gtk
import matplotlib.pyplot as plt
import sasgui
import gobject
import numpy as np
import gc
from ..hardware import sample
import logging
import sastool

logger = logging.getLogger('beamalignment')
# logger.setLevel(logging.INFO)


class BeamAlignment(gtk.Dialog):
    _images_pending = []
    def __init__(self, credo, title='Beam alignment', parent=None, flags=0, buttons=(gtk.STOCK_EXECUTE, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.credo = credo
        vb = self.get_content_area()
        tab = gtk.Table()
        self.entrytable = tab
        vb.pack_start(tab, False)
        self.set_resizable(False)
        row = 0
        
        l = gtk.Label('Sample name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.samplename_entry = gtk.Entry()
        self.samplename_entry.set_text('-- please fill --')
        tab.attach(self.samplename_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Exposure time (s):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.exptime_entry = gtk.SpinButton(gtk.Adjustment(0.1, 0, 100, 0.1, 1), digits=4)
        tab.attach(self.exptime_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Number of exposures:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.nimages_entry = gtk.SpinButton(gtk.Adjustment(1, 1, 10000, 1, 10), digits=0)
        tab.attach(self.nimages_entry, 1, 2, row, row + 1)
        row += 1
        
        self.plot_checkbutton = gtk.CheckButton('Plot after exposure')
        self.plot_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.plot_checkbutton, 0, 2, row, row + 1)
        self.plot_checkbutton.set_active(True)
        row += 1

        self.reuse_checkbutton = gtk.CheckButton('Re-use plot')
        self.reuse_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.reuse_checkbutton, 0, 2, row, row + 1)
        self.reuse_checkbutton.set_active(True)
        row += 1

        
        self.beamposframe = gtk.Frame('Beam position finding')
        vb.pack_start(self.beamposframe, False)
        tab = gtk.Table()
        self.beamposframe.add(tab)
        row = 0
        
        l = gtk.Label(u'Beam area top:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.pri_top_entry = gtk.SpinButton(gtk.Adjustment(0, -10000, 10000, 0.1, 1), digits=2)
        tab.attach(self.pri_top_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label(u'Beam area bottom:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.pri_bottom_entry = gtk.SpinButton(gtk.Adjustment(0, -10000, 10000, 0.1, 1), digits=2)
        tab.attach(self.pri_bottom_entry, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label(u'Beam area left:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.pri_left_entry = gtk.SpinButton(gtk.Adjustment(0, -10000, 10000, 0.1, 1), digits=2)
        tab.attach(self.pri_left_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label(u'Beam area right:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.pri_right_entry = gtk.SpinButton(gtk.Adjustment(0, -10000, 10000, 0.1, 1), digits=2)
        tab.attach(self.pri_right_entry, 1, 2, row, row + 1)
        row += 1

        b = gtk.Button('Set\nfrom\ncurrent\nzoom')
        tab.attach(b, 2, 3, 0, row, gtk.FILL, gtk.FILL)
        b.connect('clicked', self.on_set_limits_from_zoom)


        self.threshold_checkbutton = gtk.CheckButton(u'Relative intensity threshold:')
        self.threshold_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.threshold_checkbutton, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.threshold_entry = gtk.SpinButton(gtk.Adjustment(0.05, 0, 1, 0.1, 1), digits=2)
        tab.attach(self.threshold_entry, 1, 2, row, row + 1)
        self.threshold_checkbutton.connect('toggled', self.on_threshold_toggled, self.threshold_entry)
        self.on_threshold_toggled(self.threshold_checkbutton, self.threshold_entry)
        row += 1
        
        f = gtk.Frame('Found position:')
        vb.pack_start(f, False)
        self.beamposlabel = gtk.Label('No position yet.')
        f.add(self.beamposlabel)
        self.beamposlabel.set_alignment(0, 0.5)
        
        self.connect('response', self.on_response)
        self.connect('delete-event', self.hide_on_delete)
        vb.show_all()
    def on_threshold_toggled(self, cb, entry):
        entry.set_sensitive(cb.get_active())
    def on_set_limits_from_zoom(self, widget):
        ax = sasgui.PlotSASImageWindow.get_current_plot().get_axes().axis()
        for sb, val in zip([self.pri_left_entry, self.pri_right_entry, self.pri_bottom_entry, self.pri_top_entry], ax):
            sb.set_value(val)
    def on_response(self, dialog, respid):
        if respid == gtk.RESPONSE_OK:
            if self.beamposframe.get_sensitive():
                self.beamposframe.set_sensitive(False)
                self.entrytable.set_sensitive(False)
                self.get_widget_for_response(gtk.RESPONSE_CANCEL).set_sensitive(False)
                self.credo.set_sample(sample.SAXSSample(self.samplename_entry.get_text()))
                self.credo.set_fileformat('beamtest', 5)

                def _handler(imgdata):
                    gobject.idle_add(self.on_imagereceived, imgdata)
                    return False
                self._images_pending = []
                self._primask = None
                self.credo.expose(self.exptime_entry.get_value(), self.nimages_entry.get_value_as_int(), blocking=False, callback=_handler)
                self.get_widget_for_response(gtk.RESPONSE_OK).set_label(gtk.STOCK_STOP)
            else:
                self.credo.killexposure()
                self.on_imagereceived(None)
        else:
            self.hide()
        return True
    def on_imagereceived(self, imgdata):
        pri = (self.pri_top_entry.get_value(),
             self.pri_bottom_entry.get_value(),
             self.pri_left_entry.get_value(),
             self.pri_right_entry.get_value())
        if imgdata is None:  # exposure failed
            logger.debug('exposure broken.')
        else:
            logger.debug('image received.')
            self._images_pending.append(imgdata)
            if self._primask is None:
                self._primask = sastool.classes.SASMask(imgdata.shape)
                self._primask.edit_rectangle(pri[0], pri[2], pri[1], pri[3], whattodo='unmask')
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
                    win.plot.gca().axis((pri[2], pri[3], pri[1], pri[0]))
                    win.plot.canvas.draw()
            if len(self._images_pending) < self.nimages_entry.get_value_as_int():
                return False
        logger.debug('last image received, analyzing images.')
        self.beamposframe.set_sensitive(True)
        self.entrytable.set_sensitive(True)
        self.get_widget_for_response(gtk.RESPONSE_CANCEL).set_sensitive(True)
        self.get_widget_for_response(gtk.RESPONSE_OK).set_label(gtk.STOCK_EXECUTE)
        
        if self.threshold_checkbutton.get_active():
            threshold = self.threshold_entry.get_value()
        else:
            threshold = None
        bcx = []
        bcy = []
        Imax = []
        Isum = []
        Imean = []
        Istd = []
        for ex in self._images_pending:
            try:
                bx, by = ex.find_beam_semitransparent(pri, threshold)
                if self._primask is not None:
                    Imax.append(ex.max(mask=self._primask))
                    Isum.append(ex.sum(mask=self._primask))
                    Imean.append(ex.mean(mask=self._primask))
                    Istd.append(ex.std(mask=self._primask))
                else:
                    Imax.append(ex.Intensity.max())
                bcx.append(bx); bcy.append(by)
            except Exception as ex:
                print ex.message
                pass
        if bcx and bcy and Imax:
            self.beamposlabel.set_text('X (row): ' + str(np.mean(bcx)) + ' +/- ' + str(np.std(bcx)) + ' (from ' + str(len(bcx)) + ' data)' + 
                                       '\nY (column): ' + str(np.mean(bcy)) + ' +/- ' + str(np.std(bcy)) + ' (from ' + str(len(bcy)) + ' data)' + 
                                       '\nMax. intensity: ' + str(np.mean(Imax)) + ' +/- ' + str(np.std(Imax)) + ' (from ' + str(len(Imax)) + ' data)' + 
                                       '\nSum intensity: ' + str(np.mean(Isum)) + ' +/- ' + str(np.std(Isum)) + ' ( from ' + str(len(Isum)) + ' data)' + 
                                       '\nMean intensity: ' + str(np.mean(Imean)) + ' +/- ' + str(np.std(Imean)) + ' ( from ' + str(len(Imean)) + ' data)' + 
                                       '\nStddev intensity: ' + str(np.mean(Istd)) + ' +/- ' + str(np.std(Istd)) + ' ( from ' + str(len(Istd)) + ' data)' + 
                                       '\nFiles loaded: ' + str(len(self._images_pending)))
            logger.debug('BeamX: %f; BeamY: %f; Imax: %f; Isum: %f; Imean: %f; Istd: %f' % (np.mean(bcx), np.mean(bcy), np.mean(Imax), np.mean(Isum), np.mean(Imean), np.mean(Istd)))
        else:
            self.beamposlabel.set_text('Error in beam positioning, try to disable or tune threshold.')
        self._images_pending = []
        self._primask = None
        gc.collect()
        return False
    
