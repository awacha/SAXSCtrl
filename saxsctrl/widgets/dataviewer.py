import gtk
import sasgui
import gobject
import sastool

class DataViewer(gtk.Dialog):
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
        self.fileprefix_entry = gtk.Entry()
        self.fileprefix_entry.set_text('crd_%05d')
        tab.attach(self.fileprefix_entry, 1, 2, row, row + 1)
        row += 1
    
        def _handler(widget):
            filename = self.fileprefix_entry.get_text() % (self.fsn_entry.get_value_as_int()) + '.cbf'
            gobject.idle_add(self.on_open, filename)
            return True
    
        l = gtk.Label(u'FSN:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.fsn_entry = gtk.SpinButton(gtk.Adjustment(1, 0, 1e6, 1, 10), digits=0)
        tab.attach(self.fsn_entry, 1, 2, row, row + 1)
        self.fsn_entry.connect('changed', _handler)
        row += 1

        b = gtk.Button(stock=gtk.STOCK_OPEN)
        tab.attach(b, 2, 3, 0, row)
        b.connect('clicked', _handler)

        l = gtk.Label(u'Mask file name:');l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.mask_entry = gtk.Entry()
        self.mask_entry.set_text('mask.mat')
        tab.attach(self.mask_entry, 1, 2, row, row + 1)
        row += 1

        b = gtk.Button(stock=gtk.STOCK_EDIT)
        tab.attach(b, 2, 3, row - 1, row)
        b.connect('clicked', self.on_editmask)
         

        
        self.plot2d = sasgui.PlotSASImage()
        vb.pack_start(self.plot2d, True)
        self.connect('response', self.on_response)
        self.connect('delete-event', self.hide_on_delete)
        
        vb.show_all()
    def on_open(self, filename):
        datadirs = sastool.misc.find_subdirs(self.credo.filepath) + [self.credo.imagepath]
        if sastool.misc.findfileindirs(self.mask_entry.get_text(), datadirs, notfound_is_fatal=False, notfound_val=None) is None:
            loadmask = False
        else:
            loadmask = True
        try:
            ex = sastool.classes.SASExposure(filename, dirs=datadirs, maskfile=self.mask_entry.get_text(), load_mask=loadmask)
        except IOError:
            raise
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
        
