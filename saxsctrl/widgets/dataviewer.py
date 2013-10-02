from gi.repository import Gtk
import sasgui
import sastool
import os
from .exposureselector import ExposureSelector
import qrcode
from .widgets import ToolDialog

class DataViewer(ToolDialog):
    _filechooserdialogs = None
    _datared_jobidx = 0
    _datared_connections = None
    def __init__(self, credo, title='Data display'):
        ToolDialog.__init__(self, credo, title)
        self.datareduction = None
        vb = self.get_content_area()
        
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, False, True, 0)
        self._exposureselector = ExposureSelector(self.credo)
        self._exposureselector.connect('open', self._exposure_open)
        hb.pack_start(self._exposureselector, True, True, 0)
        
        
        f = Gtk.Frame(label='Currently loaded:')
        hb.pack_start(f, True, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        
        row = 0
        self._labels = {}
        for labeltext, labelname in [('FSN:', 'fsn'), ('Sample-detector distance:', 'dist'), ('Title:', 'title'), ('Owner:', 'owner'), ('Exposure time:', 'meastime'), ('Temperature', 'temperature')]:
            l = Gtk.Label(labeltext); l.set_alignment(0, 0.5)
            tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
            self._labels[labelname] = Gtk.Label('<none>')
            self._labels[labelname].set_alignment(0, 0.5)
            tab.attach(self._labels[labelname], 1, 2, row, row + 1, xpadding=5)
            row += 1
        b = Gtk.Button(label='Data reduction...')
        tab.attach(b, 2, 3, 0, row, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b.connect('clicked', self.do_data_reduction)
        l = Gtk.Label('Mask:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._labels['maskid'] = Gtk.Label('<none>')
        self._labels['maskid'].set_alignment(0, 0.5)
        tab.attach(self._labels['maskid'], 1, 2, row, row + 1, xpadding=5)

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
        
        
        vb.show_all()
    def on_data_reduction_finished(self, ssdr, fsn, header, button, fsn_to_wait_for):
        if fsn != fsn_to_wait_for:
            return False
        ssdr.disconnect(self._dr_connid)
        self._exposureselector.set_sensitive(True)
        button.set_sensitive(True)
        exposure = ssdr.beamtimereduced.load_exposure(fsn)
        self.plot1d.add_curve_with_errorbar(exposure.radial_average(), label='Reduced: ' + str(exposure.header))
        self.plot2d.set_exposure(exposure)
        return False
    def do_data_reduction(self, button):
        if self.plot2d.exposure is None:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Please open a file first!')
            md.run()
            md.destroy()
            del md
            return
        ssdr = self.credo.subsystems['DataReduction']
        if not os.path.split(self.plot2d.exposure['FileName'])[1].startswith(ssdr.filebegin):
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot do data reduction on exposure. File must begin with %s' % ssdr.filebegin)
            md.run()
            md.destroy()
            del md
            return
        button.set_sensitive(False)
        self._exposureselector.set_sensitive(False)
        self._dr_connid = ssdr.connect('done', self.on_data_reduction_finished, button, self.plot2d.exposure['FSN'])
        ssdr.reduce(self.plot2d.exposure['FSN'])
    def _exposure_open(self, eselector, ex):
        self._labels['fsn'].set_label(str(ex['FSN']))
        self._labels['title'].set_label(ex['Title'])
        self._labels['dist'].set_label(str(ex['Dist']))
        try:
            self._labels['temperature'].set_label(str(ex['Temperature']))
        except KeyError:
            self._labels['temperature'].set_label('<none>')
        if ex['maskid'] is None:
            self._labels['maskid'].set_label('<none>')
        else:
            self._labels['maskid'].set_label(ex['maskid'])
        self._labels['meastime'].set_label(str(ex['MeasTime']))
        self._labels['owner'].set_label(ex['Owner'])
        self.plot2d.set_exposure(ex)
        self.plot2d.set_bottomrightdata(ex['Owner'] + '@CREDO ' + str(ex['Date']))
        self.plot2d.set_bottomleftdata(qrcode.make(ex['Owner'] + '@CREDO://' + str(ex.header) + ' ' + str(ex['Date']), box_size=10))
        try:
            rad = ex.radial_average()
        except sastool.classes.SASExposureException as see:
            self.plot1d.gca().text(0.5, 0.5, 'Cannot do radial average:\n' + str(see), ha='center', va='center', transform=self.plot1d.gca().transAxes)
        else:
            self.plot1d.add_curve_with_errorbar(rad, label=str(ex.header))
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
        
