from gi.repository import Gtk
import sasgui
from gi.repository import GObject
import sastool
import re
import os
from .spec_filechoosers import MaskChooserDialog
from .exposureselector import ExposureSelector
import datetime
from .data_reduction_setup import DataRedSetup, PleaseWaitDialog
from ..hardware.subsystems.datareduction import DataReduction
import qrcode

class DataViewer(Gtk.Dialog):
    _filechooserdialogs = None
    _datared_jobidx = 0
    _datared_connections = None
    def __init__(self, credo, title='Data display', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        self.credo = credo
        self.datareduction = None
        vb = self.get_content_area()
        
        es = ExposureSelector(self.credo)
        es.connect('open', self._exposure_open)
        vb.pack_start(es, False, True, 0)
        
        
        f = Gtk.Frame(label='Currently loaded:')
        vb.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        
        row = 0
        self._labels = {}
        for labeltext, labelname in [('FSN:', 'fsn'), ('Sample-detector distance:', 'dist'), ('Title:', 'title'), ('Owner:', 'owner'), ('Exposure time:', 'meastime')]:
            l = Gtk.Label(labeltext); l.set_alignment(0, 0.5)
            tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
            self._labels[labelname] = Gtk.Label('<none>')
            self._labels[labelname].set_alignment(0, 0.5)
            tab.attach(self._labels[labelname], 1, 2, row, row + 1)
            row += 1
        b = Gtk.Button(label='Data reduction...')
        tab.attach(b, 2, 3, 0, row, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b.connect('clicked', self.do_data_reduction)
        l = Gtk.Label('Mask:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._labels['maskid'] = Gtk.Label('<none>')
        self._labels['maskid'].set_alignment(0, 0.5)
        tab.attach(self._labels['maskid'], 1, 2, row, row + 1)

        hbb = Gtk.HButtonBox()
        tab.attach(hbb, 2, 3, row, row + 1, Gtk.AttachOptions.FILL)
        hbb.set_layout(Gtk.ButtonBoxStyle.SPREAD)
        b = Gtk.Button(stock=Gtk.STOCK_EDIT)
        b.connect('clicked', self._editmask)
        hbb.pack_start(b, True, True, 0)
        row += 1
        
        p = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(p, True, True, 0)
        self.plot2d = sasgui.PlotSASImage()
        self.plot2d.set_size_request(200, -1)
        p.pack1(self.plot2d, True, False)
        self.plot1d = sasgui.PlotSASCurve()
        self.plot1d.set_size_request(200, -1)
        p.pack2(self.plot1d, True, False)
        p.set_size_request(-1, 480)
        self.connect('response', self.on_response)
        # self.connect('delete-event', self.hide_on_delete)
        
        
        vb.show_all()
    def on_data_reduction_callback(self, datared, idx, message_or_exposure):
        if idx != self._datared_jobidx:
            return False
        if (not hasattr(self, '_pwd')) or (self._pwd is None):
            return False
        if isinstance(message_or_exposure, basestring):
            self._pwd.set_label_text(message_or_exposure)
            return False
        for c in self._datared_connections:
            self.datareduction.disconnect(c)
        self._datared_connections = None
        self._pwd.destroy()
        del self._pwd
        message_or_exposure.write(os.path.join(self.credo.eval2dpath, 'crd_%05d.h5' % message_or_exposure['FSN']))
        rad = message_or_exposure.radial_average()
        rad.save(os.path.join(self.credo.eval1dpath, 'crd_%05d.txt' % message_or_exposure['FSN']))
        self.plot1d.cla()
        self.plot1d.loglog(rad)
        self.plot2d.set_exposure(message_or_exposure)
        return False
    def do_data_reduction(self, button):
        if self._datared_connections is not None:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Another data reduction procedure is running!')
            md.run()
            md.destroy()
            del md
            return
        if self.plot2d.exposure is None:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Please open a file first!')
            md.run()
            md.destroy()
            del md
            return
        exposure = self.plot2d.exposure
        if self.datareduction is None:
            self.datareduction = DataReduction(self.credo.datareduction)
            self._dataredsetup = DataRedSetup(self, 'Data reduction parameters for ' + str(exposure.header), buttons=(Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        self._dataredsetup.present()
        resp = self._dataredsetup.run()
        if resp == Gtk.ResponseType.OK:
            self._pwd = PleaseWaitDialog()
            def cb(msg):
                GObject.idle_add(self.on_data_reduction_callback, msg)
            self._pwd.show_all()
            self._datared_connections = (self.datareduction.connect('message', self.on_data_reduction_callback),
                                       self.datareduction.connect('done', self.on_data_reduction_callback))
            self._datared_jobidx = self.datareduction.do_reduction(self.plot2d.exposure)
        self._dataredsetup.hide()
    def _exposure_open(self, eselector, ex):
        self._labels['fsn'].set_label(str(ex['FSN']))
        self._labels['title'].set_label(ex['Title'])
        self._labels['dist'].set_label(str(ex['Dist']))
        if ex['maskid'] is None:
            self._labels['maskid'].set_label('<none>')
        else:
            self._labels['maskid'].set_label(ex['maskid'])
        self._labels['meastime'].set_label(str(ex['MeasTime']))
        self._labels['owner'].set_label(ex['Owner'])
        self.plot2d.set_exposure(ex)
        self.plot2d.set_bottomrightdata(ex['Owner'] + '@CREDO ' + str(ex['Date']))
        self.plot2d.set_bottomleftdata(qrcode.make(ex['Owner'] + '@CREDO://' + str(ex.header) + ' ' + str(ex['Date']), box_size=10))
        self.plot1d.cla()
        try:
            rad = ex.radial_average()
        except sastool.classes.SASExposureException as see:
            self.plot1d.gca().text(0.5, 0.5, 'Cannot do radial average:\n' + see.message, ha='center', va='center', transform=self.plot1d.gca().transAxes)
        else:
            self.plot1d.cla()
            self.plot1d.loglog(ex.radial_average())
            self.plot1d.legend(loc='best')
        return False
    def _editmask(self, widget):
        maskmaker = sasgui.maskmaker.MaskMaker(matrix=self.plot2d.exposure)
        resp = maskmaker.run()
        if resp == Gtk.ResponseType.OK:
            ex = self.plot2d.exposure
            ex.set_mask(maskmaker.mask)
            self.plot2d.set_exposure(ex)
        maskmaker.destroy()
        return
    def on_response(self, dialog, respid):
        self.hide()
        
