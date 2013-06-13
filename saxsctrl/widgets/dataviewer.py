from gi.repository import Gtk
import sasgui
from gi.repository import GObject
import sastool
import re
import os
from .spec_filechoosers import MaskChooserDialog
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
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        row = 0
        
        l = Gtk.Label(label=u'File prefix:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.fileprefix_entry = Gtk.ComboBoxText.new_with_entry()
        self.fileprefix_entry.append_text('crd_%05d')
        self.fileprefix_entry.append_text('beamtest_%05d')
        self.fileprefix_entry.append_text('transmission_%05d')
        self.fileprefix_entry.append_text('timedscan_%05d')
        self.fileprefix_entry.set_active(0)
        tab.attach(self.fileprefix_entry, 1, 2, row, row + 1)
        row += 1
    
    
        l = Gtk.Label(label=u'FSN:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.fsn_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 0, 1e6, 1, 10), digits=0)
        tab.attach(self.fsn_entry, 1, 2, row, row + 1)
        self.fsn_entry.connect('activate', self._openbutton_handler, 'selected')
        self.fsn_entry.connect('value-changed', self._openbutton_handler, 'selected')
        hbb = Gtk.HButtonBox()
        tab.attach(hbb, 2, 3, row - 1, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b = Gtk.Button(stock=Gtk.STOCK_GOTO_FIRST)
        hbb.add(b)
        b.connect('clicked', self._openbutton_handler, 'first')
        b = Gtk.Button(stock=Gtk.STOCK_OPEN)
        hbb.add(b)
        b.connect('clicked', self._openbutton_handler, 'selected')    
        b = Gtk.Button(stock=Gtk.STOCK_GOTO_LAST)
        hbb.add(b)
        b.connect('clicked', self._openbutton_handler, 'last')
        b = Gtk.Button(label='Data reduction...')
        hbb.add(b)
        b.connect('clicked', self.do_data_reduction)
        row += 1


        self.mask_cb = Gtk.CheckButton(label=u'Mask file name:'); self.mask_cb.set_alignment(0, 0.5)
        tab.attach(self.mask_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        hb = Gtk.HBox()
        tab.attach(hb, 1, 3, row, row + 1)
        self.mask_entry = Gtk.Entry()
        self.mask_entry.set_text(os.path.join(self.credo.maskpath, 'mask.mat'))
        hb.pack_start(self.mask_entry, True, True, 0)
        self.mask_cb.connect('toggled', self.on_checkbox_with_entry, self.mask_entry)
        self.on_checkbox_with_entry(self.mask_cb, self.mask_entry)
        
        
        hbb = Gtk.HButtonBox()
        hbb.set_layout(Gtk.ButtonBoxStyle.SPREAD)
        hb.pack_start(hbb, False, True, 0)
        b = Gtk.Button(stock=Gtk.STOCK_OPEN)
        b.connect('clicked', self.on_loadmaskbutton, self.mask_entry, Gtk.FileChooserAction.OPEN)
        hbb.pack_start(b, True, True, 0)
        b = Gtk.Button(stock=Gtk.STOCK_EDIT)
        b.connect('clicked', self.on_editmask)
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
    def on_checkbox_with_entry(self, cb, entry):
        entry.set_sensitive(cb.get_active())
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
    def _openbutton_handler(self, widget, mode):
        if mode == 'selected':
            filename = self.fileprefix_entry.get_active_text() % (self.fsn_entry.get_value_as_int()) + '.cbf'
            GObject.idle_add(self.on_open, filename)
        else:
            if mode == 'back':
                self.fsn_entry.spin(Gtk.SpinType.STEP_BACKWARD, 1)
                self._openbutton_handler(widget, 'selected')
            elif mode == 'forward':
                self.fsn_entry.spin(Gtk.SpinType.STEP_FORWARD, 1)
                self._openbutton_handler(widget, 'selected')
            else:
                pattern = re.compile(sastool.misc.re_from_Cformatstring_numbers(self.fileprefix_entry.get_active_text())[:-1])
                maxfsn = -1
                minfsn = 9999999999999
                for pth in self.credo.get_exploaddirs():
                    fsns = [int(f.group(1)) for f in [pattern.match(f) for f in os.listdir(pth)] if f is not None]
                    if not fsns:
                        continue
                    maxfsn = max(maxfsn, max(fsns))
                    minfsn = min(minfsn, min(fsns))
                if mode == 'first':
                    if minfsn >= 9999999999999:
                        return False
                    self.fsn_entry.set_value(minfsn)
                    self._openbutton_handler(widget, 'selected')
                elif mode == 'last':
                    if maxfsn < 0:
                        return False
                    self.fsn_entry.set_value(maxfsn)
                    self._openbutton_handler(widget, 'selected')
        return True
    def on_open(self, filename):
        datadirs = self.credo.get_exploaddirs()
        kwargs_to_loader = {'dirs':datadirs, 'load_mask':True}
        if self.mask_cb.get_active() and sastool.misc.findfileindirs(self.mask_entry.get_text(), datadirs, notfound_is_fatal=False, notfound_val=None) is not None:
            kwargs_to_loader['maskfile'] = self.mask_entry.get_text()
        try:
            ex = sastool.classes.SASExposure(filename, **kwargs_to_loader)
        except IOError as ioe:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Error reading file: ' + ioe.message)
            md.run()
            md.destroy()
            del md
        else:
            self.plot2d.set_exposure(ex)
            self.plot2d.set_bottomrightdata(ex['Owner'] + '@CREDO ' + str(ex['Date']))
            self.plot2d.set_bottomleftdata(qrcode.make(ex['Owner'] + '@CREDO://' + str(ex.header) + ' ' + str(ex['Date']), box_size=10))
            self.plot1d.cla()
            try:
                rad = ex.radial_average()
            except sastool.classes.SASExposureException:
                self.plot1d.gca().text(0.5, 0.5, 'No mask - no radial average.', ha='center', va='center', transform=self.plot1d.gca().transAxes)
            else:
                self.plot1d.cla()
                self.plot1d.loglog(ex.radial_average())
                self.plot1d.legend(loc='best')
        return False
    def on_editmask(self, widget):
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
        
