
from gi.repository import Gtk
from gi.repository import GLib
import logging
from .nextfsn_monitor import NextFSNMonitor
from .samplesetup import SampleSelector
from .widgets import ToolDialog
from .exposure import ExposureFrame

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
import sasgui.libconfig

class SingleExposure(ToolDialog):
    _filechooserdialogs = None
    def __init__(self, credo, title='Single exposure'):
        ToolDialog.__init__(self, credo, title, buttons=('Execute', Gtk.ResponseType.OK, 'Close', Gtk.ResponseType.CLOSE))
        vb = self.get_content_area()

        self.entrygrid = Gtk.Grid()
        vb.pack_start(self.entrygrid, False, True, 0)
        self.set_resizable(False)
        row = 0

        l = Gtk.Label(label='Sample:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        self.entrygrid.attach(l, 0, row, 1, 1)
        self.sample_combo = SampleSelector(self.credo)
        self.entrygrid.attach(self.sample_combo, 1, row, 1, 1)
        row += 1

        self.expframe = ExposureFrame(self.credo)
        self.entrygrid.attach(self.expframe, 0, row, 2, 1)
        self._conns = [self.expframe.connect('started', self._on_start),
                       self.expframe.connect('end', self._on_end),
                       self.expframe.connect('image', self._on_image),
                      ]
        row += 1

        f = Gtk.Frame(label='2D plot')
        vb.pack_start(f, False, True, 0)

        vb1 = Gtk.VBox()
        f.add(vb1)
        self.plot2D_checkbutton = Gtk.CheckButton('Plot image afterwards'); self.plot2D_checkbutton.set_halign(Gtk.Align.START)
        vb1.pack_start(self.plot2D_checkbutton, True, True, 0)
        self.plot2D_checkbutton.set_active(True)
        self.reuse2D_checkbutton = Gtk.CheckButton('Re-use plot window'); self.reuse2D_checkbutton.set_halign(Gtk.Align.START)
        vb1.pack_start(self.reuse2D_checkbutton, True, True, 0)
        self.reuse2D_checkbutton.set_active(True)

        f = Gtk.Frame(label='1D plot')
        vb.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0

        self.plot1D_checkbutton = Gtk.CheckButton('Plot curve afterwards'); self.plot1D_checkbutton.set_halign(Gtk.Align.START)
        tab.attach(self.plot1D_checkbutton, 0, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        self.plot1D_checkbutton.set_active(True)
        self.reuse1D_checkbutton = Gtk.CheckButton('Re-use plot window'); self.reuse1D_checkbutton.set_halign(Gtk.Align.START)
        self.reuse1D_checkbutton.set_active(True)
        tab.attach(self.reuse1D_checkbutton, 0, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1

        self.q_or_pixel_checkbutton = Gtk.CheckButton('Q on abscissa'); self.q_or_pixel_checkbutton.set_halign(Gtk.Align.START)
        tab.attach(self.q_or_pixel_checkbutton, 0, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1

        l = Gtk.Label(label='Plot method:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.plot1d_method = Gtk.ComboBoxText()
        tab.attach(self.plot1d_method, 1, 2, row, row + 1)
        self.plot1d_method.append_text('plot')
        self.plot1d_method.append_text('semilogx')
        self.plot1d_method.append_text('semilogy')
        self.plot1d_method.append_text('loglog')
        self.plot1d_method.set_active(3)

        vb.pack_start(NextFSNMonitor(self.credo, 'Next exposure'), True, True, 0)

        self._expsleft = 0

    def do_destroy(self):
        if hasattr(self, '_conns'):
            for c in self._conns:
                self.expframe.disconnect(c)
            del self._conns

    def do_response(self, respid):
        if respid == Gtk.ResponseType.OK:
            if self.get_widget_for_response(Gtk.ResponseType.OK).get_label() == 'Execute':
                sam = self.sample_combo.get_sample()
                logger.info('Starting single exposure on sample: ' + str(sam))
                self.credo.subsystems['Samples'].set(sam)
                if sam.title != self.credo.subsystems['Exposure'].dark_sample_name:
                    self.credo.subsystems['Samples'].moveto(blocking=True)
                else:
                    logger.info('Not moving motor, since this is the dark sample.')
                # make an exposure
                self.expframe.execute(write_nexus=True)
            else:
                # break the exposure
                self.expframe.kill()
        elif respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            self.destroy()
    def _on_start(self, expframe):
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label('Stop')
        for w in [self.entrygrid]:
            w.set_sensitive(False)
        pass
    def _on_end(self, expframe, state):
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label('Execute')
        for w in [self.entrygrid]:
            w.set_sensitive(True)
    def _on_image(self, expframe, exposure):
        logger.debug('Image received.')
        GLib.idle_add(self.plot_image, exposure)

    def plot_image(self, exposure):
        logger.debug('Plotting image.')
        if self.plot2D_checkbutton.get_active():
            if self.reuse2D_checkbutton.get_active():
                win = sasgui.plot2dsasimage.PlotSASImageWindow.get_current_plot()
            else:
                win = sasgui.plot2dsasimage.PlotSASImageWindow()
            win.set_exposure(exposure)
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
                win.set_xlabel(u'q (' + sasgui.libconfig.qunit() + ')')
            else:
                win.set_xlabel(u'Radial pixel number')
            win.set_ylabel('Intensity (total counts)')
            win.show_all()
            win.present()
        return False
