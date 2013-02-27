import gtk
import sasgui
import gobject
import sastool
import re
import os
from .spec_filechoosers import MaskChooserDialog

class DataViewer(gtk.Dialog):
    _filechooserdialogs = None
    def __init__(self, credo, title='Data display', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.credo = credo
        vb = self.get_content_area()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        row = 0
        
        l = gtk.Label(u'File prefix:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.fileprefix_entry = gtk.combo_box_entry_new_text()
        self.fileprefix_entry.append_text('crd_%05d')
        self.fileprefix_entry.append_text('beamtest_%05d')
        self.fileprefix_entry.append_text('transmission_%05d')
        self.fileprefix_entry.append_text('timedscan_%05d')
        self.fileprefix_entry.set_active(0)
        tab.attach(self.fileprefix_entry, 1, 2, row, row + 1)
        row += 1
    
    
        l = gtk.Label(u'FSN:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.fsn_entry = gtk.SpinButton(gtk.Adjustment(1, 0, 1e6, 1, 10), digits=0)
        tab.attach(self.fsn_entry, 1, 2, row, row + 1)
        self.fsn_entry.connect('activate', self._openbutton_handler, 'selected')
        hbb = gtk.HButtonBox()
        tab.attach(hbb, 2, 3, row - 1, row + 1, gtk.FILL, gtk.FILL)
        b = gtk.Button(stock=gtk.STOCK_GOTO_FIRST)
        hbb.add(b)
        b.connect('clicked', self._openbutton_handler, 'first')
        b = gtk.Button(stock=gtk.STOCK_GO_BACK)
        hbb.add(b)
        b.connect('clicked', self._openbutton_handler, 'back')
        b = gtk.Button(stock=gtk.STOCK_OPEN)
        hbb.add(b)
        b.connect('clicked', self._openbutton_handler, 'selected')    
        b = gtk.Button(stock=gtk.STOCK_GO_FORWARD)
        hbb.add(b)
        b.connect('clicked', self._openbutton_handler, 'forward')
        b = gtk.Button(stock=gtk.STOCK_GOTO_LAST)
        hbb.add(b)
        b.connect('clicked', self._openbutton_handler, 'last')
        
        row += 1


        l = gtk.Label(u'Mask file name:');l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        hb = gtk.HBox()
        tab.attach(hb, 1, 3, row, row + 1)
        self.mask_entry = gtk.Entry()
        self.mask_entry.set_text(os.path.join(self.credo.maskpath, 'mask.mat'))
        hb.pack_start(self.mask_entry)
        
        hbb = gtk.HButtonBox()
        hbb.set_layout(gtk.BUTTONBOX_SPREAD)
        hb.pack_start(hbb, False)
        b = gtk.Button(stock=gtk.STOCK_OPEN)
        b.connect('clicked', self.on_loadmaskbutton, self.mask_entry, gtk.FILE_CHOOSER_ACTION_OPEN)
        hbb.pack_start(b)
        b = gtk.Button(stock=gtk.STOCK_EDIT)
        b.connect('clicked', self.on_editmask)
        hbb.pack_start(b)
        row += 1
         

        
        self.plot2d = sasgui.PlotSASImage()
        vb.pack_start(self.plot2d, True)
        self.connect('response', self.on_response)
        self.connect('delete-event', self.hide_on_delete)
        
        vb.show_all()
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
    def _openbutton_handler(self, widget, mode):
        if mode == 'selected':
            filename = self.fileprefix_entry.get_active_text() % (self.fsn_entry.get_value_as_int()) + '.cbf'
            gobject.idle_add(self.on_open, filename)
        else:
            if mode == 'back':
                self.fsn_entry.spin(gtk.SPIN_STEP_BACKWARD, 1)
                self._openbutton_handler(widget, 'selected')
            elif mode == 'forward':
                self.fsn_entry.spin(gtk.SPIN_STEP_FORWARD, 1)
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
        if sastool.misc.findfileindirs(self.mask_entry.get_text(), datadirs, notfound_is_fatal=False, notfound_val=None) is None:
            loadmask = False
        else:
            loadmask = True
        try:
            ex = sastool.classes.SASExposure(filename, dirs=datadirs, maskfile=self.mask_entry.get_text(), load_mask=loadmask)
        except IOError as ioe:
            md = gtk.MessageDialog(self, gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, 'Error reading file: ' + ioe.message)
            md.run()
            md.destroy()
            del md
        else:
            self.plot2d.set_exposure(ex)
        return False
    def on_editmask(self, widget):
        maskmaker = sasgui.maskmaker.MaskMaker(matrix=self.plot2d.exposure)
        resp = maskmaker.run()
        if resp == gtk.RESPONSE_OK:
            ex = self.plot2d.exposure
            ex.set_mask(maskmaker.mask)
            self.plot2d.set_exposure(ex)
        maskmaker.destroy()
        return
    def on_response(self, dialog, respid):
        self.hide()
        
