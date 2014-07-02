from gi.repository import Gtk
from gi.repository import GObject
from .widgets import ToolDialog
import numpy as np
from collections import OrderedDict
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3

class Inventory(GObject.GObject):
    _items = None
    _grabbed = None
    __gsignals__ = {'items-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'grab-changed':(GObject.SignalFlags.RUN_FIRST, None, ())}
    def __init__(self, items=[]):
        GObject.GObject.__init__(self)
        self._items = dict()
        self._grabbed = dict()
        if isinstance(items, list):
            for i in items:
                self.add(i)
        elif isinstance(items, dict):
            for i in items:
                self.add(i, items[i])
    def add(self, item, multiplicity=1):
        if item not in self._items:
            self._items[item] = multiplicity
        else:
            self._items[item] += multiplicity
        if item not in self._grabbed:
            self._grabbed[item] = 0
        self.emit('items-changed')
    def remove(self, item, multiplicity=1):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        elif (self._items[item] - self._grabbed[item]) < multiplicity:
            raise KeyError('Not enough free instances of item in inventory!')
        else:
            self._items[item] -= multiplicity
            if self._items[item] < 1:
                del self._items[item]
                del self._grabbed[item]
            self.emit('items-changed')
    def grab(self, item, multiplicity=1):
        if item not in self._items:
            raise KeyError('Item %s not in inventory!' % item)
        if (self._items[item] - self._grabbed[item]) < multiplicity:
            raise KeyError('Not enough free instances of this item to grab!')
        else:
            self._grabbed[item] += 1
        self.emit('grab-changed')
    def release(self, item, multiplicity=1):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        elif self._grabbed[item] < multiplicity:
            raise KeyError('Cannot release more instances than are currently grabbed!')
        else:
            self._grabbed[item] -= multiplicity
        self.emit('grab-changed')
    def get_items(self):
        return self._items.copy()
    def get_multiplicity(self, item):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        return self._items[item]
    def get_n_free(self, item):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        return self._items[item] - self._grabbed[item]
    def get_n_grabbed(self, item):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        return self._grabbed[item]

class InventorySelectorButtons(Gtk.Grid):
    ncolumns = GObject.property(type=int, minimum=1, default=5, blurb='Number of columns')
    _inventory = None
    def __init__(self, inventory):
        Gtk.Grid.__init__(self)
        self._inventory = inventory
        self._itembuttons = []
        self._inventory.connect('items-changed', self._inventory_items_change)
        self._inventory.connect('grab-changed', self._inventory_grab_change)
        self._repopulate()
        self.show_all()
    def _inventory_items_change(self, inventory):
        self._repopulate()
    def _repopulate(self):
        for ib in self._itembuttons:
            ib.disconnect(ib._isconn)
            self.remove(ib)
            ib.destroy()
        for i in sorted(self._inventory.get_items()):
            for itemcnt in range(self._inventory.get_multiplicity(i)):
                self._itembuttons.append(Gtk.ToggleButton(label=i))
                self._itembuttons[-1]._isconn = self._itembuttons[-1].connect('toggled', self._item_button_toggled)
                self.attach(self._itembuttons[-1], (len(self._itembuttons) - 1) % self.ncolumns, (len(self._itembuttons) - 1) / self.ncolumns, 1, 1)
        self._adjust_grabs()
    def _item_button_toggled(self, button):
        if button.get_active():
            self._inventory.grab(button.get_label())
        else:
            self._inventory.release(button.get_label())

    def _adjust_grabs(self):
        for i in self._inventory.get_items():
            buttons = [b for b in self._itembuttons if b.get_label() == i]
            n_grabbed = self._inventory.get_n_grabbed(i)
            toggled_buttons = [b for b in buttons if b.get_active()]
            released_buttons = [b for b in buttons if not b.get_active()]
            n_to_be_grayed = n_grabbed - len(toggled_buttons)
            for b in toggled_buttons:
                b.set_sensitive(True)
            for idx, b in enumerate(reversed(released_buttons)):
                if idx < n_to_be_grayed:
                    b.set_sensitive(False)
                else:
                    b.set_sensitive(True)
            # we have len(buttons) buttons for this item. From these

    def do_notify(self, prop):
        if prop.name == 'ncolumns':
            self._repopulate()
    def _inventory_grab_change(self, inventory):
        return self._adjust_grabs()
    def get_selected(self):
        return [b.get_label() for b in self._itembuttons if b.get_active()]

# radius of the third pin-hole, can be calculated from R1, R2, L1, L2. The criterion is that the 3rd pin-hole
# cuts away only the parasitic scattering from R2, but does not touch the photons, which are unaffected either by R1 or R2.
calc_R3_geo = lambda R1, R2, L1, L2: R2 + L2 * (R1 + R2) / (L1 * 1.0)

# size of the beam-stop. The beam stop should cover the remaining parasitic scattering from R2.
calc_Delta_geo = lambda R1, R2, R3, L1, L2, L3: R3 * (1 + L3 / float(L2)) + R2 * (L3 / float(L2))

# effective (larger) size of the beam-stop at the detector surface
calc_Deltaprime_geo = lambda R1, R2, R3, L1, L2, L3, deltaLprime: R3 * (1 + (L3 + deltaLprime) / float(L2)) + R2 * ((L3 + deltaLprime) / float(L2))

# radius of the beam at the sample position
calc_Rsample_geo = lambda R1, R2, L1, L2, deltaL: R2 + (L2 + deltaL) * (R1 + R2) / float(L1)

# maximum divergence defined by the first two pin-holes
calc_alpha_geo = lambda R1, R2, L1: np.arctan((R1 + R2) / L1)

# maximum divergence defined by the last two pin-holes
calc_beta_geo = lambda R2, R3, L2: np.arctan((R2 + R3) / L2)

def Pinhole_MonteCarlo(R1, R2, R3, L1, L2, L3, deltaL, deltaLprime, BSsize, Nrays, beam_exit_width, beam_exit_height, beam_hwhm_divergence):
    results = OrderedDict()
    photons = np.zeros(Nrays, dtype={'names':['x', 'y', 'vx', 'vy', 'dead'], 'formats':[np.double] * 4 + [np.int8]})
    photons['x'] = np.random.randn(Nrays) * beam_exit_width / 4
    photons['y'] = np.random.randn(Nrays) * beam_exit_height / 4
    phi = np.random.rand(Nrays) * 2 * np.pi
    theta = np.random.randn(Nrays) * beam_hwhm_divergence
    # using tan(theta) in vx and vy, thus we get dx/dz and dy/dz, respectively, instead of dx/dt and dy/dt.
    photons['vx'] = np.tan(theta) * np.cos(phi)
    photons['vy'] = np.tan(theta) * np.sin(phi)
    results['Nrays'] = Nrays
    photons['dead'] = 0
    alive = (photons['dead'] == 0)

    x = photons['x']
    y = photons['y']
    # count photons which pass through R1 and kill the rest.
    beamradius = ((x ** 2 + y ** 2) ** 0.5)
    # count photons which pass through R1 and kill the rest.
    photons['dead'][alive & (beamradius > R1)] = 1
    alive = (photons['dead'] == 0)
    results['flux_after_R1'] = alive.sum()
    results['flux_rel_after_R1'] = alive.sum() / float(Nrays)

    # propagate to R2
    x = photons['x'] + photons['vx'] * L1
    y = photons['y'] + photons['vy'] * L1

    # measure beam radius at R2
    beamradius = ((x ** 2 + y ** 2) ** 0.5)
    results['R2_max_radius'] = beamradius[alive].max()
    results['R2_mean_radius'] = beamradius[alive].mean()
    # count photons which pass through R2 and kill the rest.
    photons['dead'][alive & (beamradius > R2)] = 2
    alive = (photons['dead'] == 0)
    results['flux_after_R2'] = alive.sum()
    results['flux_rel_after_R2'] = alive.sum() / float(Nrays)

    # propagate to R3
    x = photons['x'] + photons['vx'] * (L1 + L2)
    y = photons['y'] + photons['vy'] * (L1 + L2)

    # measure beam radius at R3
    beamradius = ((x ** 2 + y ** 2) ** 0.5)
    results['R3_max_radius'] = beamradius[alive].max()
    results['R3_mean_radius'] = beamradius[alive].mean()
    # count photons which pass through R3 and kill the rest.
    photons['dead'][alive & (beamradius > R3)] = 3
    alive = (photons['dead'] == 0)
    results['flux_after_R3'] = alive.sum()
    results['flux_rel_after_R3'] = alive.sum() / float(Nrays)

    # propagate to the sample
    x = photons['x'] + photons['vx'] * (L1 + L2 + deltaL)
    y = photons['y'] + photons['vy'] * (L1 + L2 + deltaL)
    # measure beam radius at sample
    beamradius = ((x ** 2 + y ** 2) ** 0.5)
    results['sample_max_radius'] = beamradius[alive].max()
    results['sample_mean_radius'] = beamradius[alive].mean()

    # propagate to the beamstop
    x = photons['x'] + photons['vx'] * (L1 + L2 + L3 - deltaLprime)
    y = photons['y'] + photons['vy'] * (L1 + L2 + L3 - deltaLprime)
    # measure beam radius at beamstop
    beamradius = ((x ** 2 + y ** 2) ** 0.5)
    results['beamstop_max_radius'] = beamradius[alive].max()
    results['beamstop_mean_radius'] = beamradius[alive].mean()

    # propagate to the detector
    x = photons['x'] + photons['vx'] * (L1 + L2 + L3)
    y = photons['y'] + photons['vy'] * (L1 + L2 + L3)
    # measure beam radius at detector
    beamradius = ((x ** 2 + y ** 2) ** 0.5)
    results['detector_max_radius'] = beamradius[alive].max()
    results['detector_mean_radius'] = beamradius[alive].mean()


    photons['dead'][alive] = 10000
    results['_rays_'] = photons
    return results

class PinHoleCalculator(ToolDialog):
    _pinhole_inventory = [150, 150, 200, 300, 300, 400, 400, 400, 500, 500, 500, 600, 600, 750, 750, 750, 1000, 1000, 1000, 1250]
    _distelement_inventory = [100, 100, 200, 200, 500, 800]
    _sddist = {'Short tube':457.121, 'Long tube':1200, 'Both tubes':1494.336}
    _R3_to_sample = 50 + 4 + 30 + 110
    _bsfront_to_detector = 54
    _beamheight = 1.5
    _beamwidth = 1
    _beamdiv = (-0.4 ** 2 / np.log(0.20) * 0.5) ** 0.5  # in mrad. GeniX has an output divergence <0.4 mrad HW20%M
    _Nrays = 1000000
    _last_results = None
    def __init__(self, credo, title='Pin-hole calculator'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        self._distelement_inventory = Inventory([str(x) for x in self._distelement_inventory])
        self._pinhole_inventory = Inventory([str(x) for x in self._pinhole_inventory])

        vb = self.get_content_area()
        grid = Gtk.Grid()
        vb.pack_start(grid, True, True, 0)
        row = 0
        l = Gtk.Label(label='Pin-hole #1 diameter (um):')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._ph1_aperture_entry = Gtk.ComboBoxText()
        for phdiam in sorted(self._pinhole_inventory.get_items(), key=lambda x:float(x)):
            self._ph1_aperture_entry.append_text(phdiam)
        self._ph1_aperture_entry.set_active(0)
        grid.attach(self._ph1_aperture_entry, 1, row, 1, 1)
        row += 1
        l = Gtk.Label(label='Pin-hole #2 diameter (um):')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._ph2_aperture_entry = Gtk.ComboBoxText()
        for phdiam in sorted(self._pinhole_inventory.get_items(), key=lambda x:float(x)):
            self._ph2_aperture_entry.append_text(phdiam)
        self._ph2_aperture_entry.set_active(0)
        grid.attach(self._ph2_aperture_entry, 1, row, 1, 1)
        row += 1
        self._ph3_manual_selector = Gtk.CheckButton(label='Pin-hole #3 diameter (um):')
        self._ph3_manual_selector.set_alignment(0, 0.5)
        grid.attach(self._ph3_manual_selector, 0, row, 1, 1)
        self._ph3_manual_selector.set_hexpand(False)
        self._ph3_aperture_entry = Gtk.ComboBoxText()
        for phdiam in sorted(self._pinhole_inventory.get_items(), key=lambda x:float(x)):
            self._ph3_aperture_entry.append_text(phdiam)
        grid.attach(self._ph3_aperture_entry, 1, row, 1, 1)
        self._ph3_manual_selector.connect('toggled', lambda button, combo: combo.set_sensitive(button.get_active()), self._ph3_aperture_entry)
        self._ph3_aperture_entry.set_sensitive(False)
        self._ph3_manual_selector.set_active(False)
        row += 1
        self._bs_manual_selector = Gtk.CheckButton(label='Beamstop diameter (mm):')
        self._bs_manual_selector.set_alignment(0, 0.5)
        grid.attach(self._bs_manual_selector, 0, row, 1, 1)
        self._bs_manual_selector.set_hexpand(False)
        self._bs_size_entry = Gtk.SpinButton(digits=2)
        grid.attach(self._bs_size_entry, 1, row, 1, 1)
        self._bs_size_entry.set_range(0, 10000)
        self._bs_size_entry.set_increments(1, 10)
        self._bs_size_entry.set_value(4)
        self._bs_manual_selector.connect('toggled', lambda button, combo: combo.set_sensitive(button.get_active()), self._bs_size_entry)
        self._bs_size_entry.set_sensitive(False)
        self._bs_manual_selector.set_active(False)
        row += 1
        l = Gtk.Label(label='Pin-hole #1-#2 distance elements:')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._ph12_dist_elements_entry = InventorySelectorButtons(self._distelement_inventory)
        grid.attach(self._ph12_dist_elements_entry, 1, row, 1, 1)
        row += 1
        l = Gtk.Label(label='Pin-hole #2-#3 distance elements:')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._ph23_dist_elements_entry = InventorySelectorButtons(self._distelement_inventory)
        grid.attach(self._ph23_dist_elements_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Sample-to-detector distance (mm):')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._sddist_entry = Gtk.ComboBoxText()
        for sdd in sorted(self._sddist):
            self._sddist_entry.append_text(sdd)
        self._sddist_entry.set_active(0)
        grid.attach(self._sddist_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Pin-hole #3-to-sample distance (mm):')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._p3_sample_dist_entry = Gtk.SpinButton(digits=2)
        self._p3_sample_dist_entry.set_range(0, 10000)
        self._p3_sample_dist_entry.set_increments(1, 10)
        self._p3_sample_dist_entry.set_value(self._R3_to_sample)
        grid.attach(self._p3_sample_dist_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Beamstop front-to-detector distance (mm):')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._bs_det_dist_entry = Gtk.SpinButton(digits=2)
        self._bs_det_dist_entry.set_range(0, 10000)
        self._bs_det_dist_entry.set_increments(1, 10)
        self._bs_det_dist_entry.set_value(self._bsfront_to_detector)
        grid.attach(self._bs_det_dist_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Beam width at X-ray generator exit (mm):')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._beamwidth_entry = Gtk.SpinButton(digits=2)
        self._beamwidth_entry.set_range(0, 10000)
        self._beamwidth_entry.set_increments(1, 10)
        self._beamwidth_entry.set_value(self._beamwidth)
        grid.attach(self._beamwidth_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Beam height at X-ray generator exit (mm):')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._beamheight_entry = Gtk.SpinButton(digits=2)
        self._beamheight_entry.set_range(0, 10000)
        self._beamheight_entry.set_increments(1, 10)
        self._beamheight_entry.set_value(self._beamheight)
        grid.attach(self._beamheight_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Beam HWHM divergence (mrad):')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._beamdiv_entry = Gtk.SpinButton(digits=4)
        self._beamdiv_entry.set_range(0, 10000)
        self._beamdiv_entry.set_increments(1, 10)
        self._beamdiv_entry.set_value(self._beamdiv)
        grid.attach(self._beamdiv_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='No. of rays for Monte Carlo:')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        l.set_hexpand(False)
        self._Nrays_entry = Gtk.SpinButton(digits=0)
        self._Nrays_entry.set_range(0, 100000000)
        self._Nrays_entry.set_increments(100, 10000)
        self._Nrays_entry.set_value(self._Nrays)
        grid.attach(self._Nrays_entry, 1, row, 1, 1)
        row += 1


        self._calc_button = Gtk.Button.new_from_icon_name('accessories-calculator', Gtk.IconSize.BUTTON)
        self._calc_button.set_label('Calculate')
        self._calc_button.connect('clicked', self._on_calc)
        grid.attach(self._calc_button, 0, row, 2, 1)

        stackcontainer = Gtk.Stack()
        stackswitcher = Gtk.StackSwitcher()
        stackswitcher.set_stack(stackcontainer)
        grid.attach(stackswitcher, 2, 0, 1, 1)
        grid.attach(stackcontainer, 2, 1, 1, row - 1)
        stackcontainer.set_hexpand(True)
        stackcontainer.set_vexpand(True)
        stackswitcher.set_hexpand(True)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        stackcontainer.add_titled(sw, 'results', 'Numeric results')
        stackcontainer.set_visible_child_name('results')
        self._results_model = Gtk.ListStore(GObject.TYPE_BOOLEAN, GObject.TYPE_STRING, GObject.TYPE_STRING)
        self._results_view = Gtk.TreeView(self._results_model)
        self._results_view.set_rules_hint(True)
        cr = Gtk.CellRendererToggle()
        cr.connect('toggled', self._on_resultline_toggled)
        self._results_view.append_column(Gtk.TreeViewColumn('', cr, active=0))
        cr.set_radio(True)
        self._results_view.append_column(Gtk.TreeViewColumn('Name', Gtk.CellRendererText(), text=1))
        self._results_view.append_column(Gtk.TreeViewColumn('Value', Gtk.CellRendererText(), text=2))
        sw.add(self._results_view)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        stackcontainer.add_titled(vbox, 'beamprofile' , 'Radial beam profile')
        stackcontainer.set_transition_duration(1000)
        stackcontainer.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(hbox, False, False, 0)
        l = Gtk.Label(label='Distance along beam:')
        l.set_alignment(0, 0.5)
        hbox.pack_start(l, False, False, 0)
        self._beampathlength_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=None)
        hbox.pack_start(self._beampathlength_scale, True, True, 0)
        self._beampathlength_scale.set_value_pos(Gtk.PositionType.RIGHT)

        self._beamprofile_plottype = Gtk.CheckButton(label='Beam map instead of radial profile')
        self._beamprofile_plottype.set_alignment(0, 0.5)
        vbox.pack_start(self._beamprofile_plottype, False, False, 0)
        self._beamprofile_plottype.connect('toggled', self._on_beampathlength_scale_value_changed)

        self._beammap_plotwidth_cb = Gtk.CheckButton(label='Width of beam map graph (mm)')
        self._beammap_plotwidth_entry = Gtk.SpinButton(digits=4)
        self._beammap_plotwidth_entry.set_range(0, 10)
        self._beammap_plotwidth_entry.set_increments(1, 10)
        self._beammap_plotwidth_entry.set_value(1)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(hbox, False, False, 0)
        hbox.pack_start(self._beammap_plotwidth_cb, False, False, 0)
        hbox.pack_start(self._beammap_plotwidth_entry, True, True, 0)
        self._beammap_plotwidth_cb.connect('toggled', lambda cb: self._beammap_plotwidth_entry.set_sensitive(cb.get_active()) and self._on_beampathlength_scale_value_changed(cb))
        self._beammap_plotwidth_entry.connect('value-changed', self._on_beampathlength_scale_value_changed)
        self._beammap_plotwidth_cb.set_active(False)
        self._beammap_plotwidth_entry.set_sensitive(False)

        self._beamprofile_fig = Figure(figsize=(3.75, 2.5), dpi=80)
        self._beamprofile_fig_canvas = FigureCanvasGTK3Agg(self._beamprofile_fig)
        vbox.pack_start(self._beamprofile_fig_canvas, True, True, 0)
        self._beamprofile_fig_toolbar = NavigationToolbar2GTK3(self._beamprofile_fig_canvas, None)
        vbox.pack_start(self._beamprofile_fig_toolbar, False, True, 0)
        self._beamprofile_axes = self._beamprofile_fig.add_subplot(111)

        self._beampathlength_scale.connect('value-changed', self._on_beampathlength_scale_value_changed)
        self.show_all()
    def _on_beampathlength_scale_value_changed(self, widget):
        if self._last_results is None:
            return False
        pos = self._beampathlength_scale.get_value()
        rays = self._last_results['_rays_']
        if pos < 0:
            # before 1st pin-hole
            pos = 0
            alive = np.ones_like(rays['dead'], dtype=np.bool)
        elif pos < self._last_results['L1']:
            # before 2nd pin-hole (and after 1st)
            alive = rays['dead'] > 1
        elif pos < self._last_results['L2']:
            # before 3rd pin-hole (and after 2nd)
            alive = rays['dead'] > 2
        else:
            # after 3rd pin-hole
            alive = rays['dead'] > 3
        r = (((rays['x'] + pos * rays['vx']) ** 2 + (rays['y'] + pos * rays['vy']) ** 2) ** 0.5)[alive]
        if not len(r):
            return
        self._beamprofile_axes.cla()
        if self._beamprofile_plottype.get_active():
            self._beamprofile_axes.plot((rays['x'] + pos * rays['vx'])[alive], (rays['y'] + pos * rays['vy'])[alive], ',')
            if self._beammap_plotwidth_cb.get_active():
                width = self._beammap_plotwidth_entry.get_value()
                self._beamprofile_axes.axis(xmin= -0.5 * width, xmax=0.5 * width, ymin= -0.5 * width, ymax=0.5 * width)
            self._beamprofile_axes.set_aspect('equal')
        else:
            self._beamprofile_axes.hist(r, 100, weights=r ** (-1))
            self._beamprofile_axes.set_aspect('auto')
        self._beamprofile_fig_canvas.draw()
    def _on_resultline_toggled(self, resultline, treepath):
        for row in self._results_model:
            row[0] = False
        self._results_model[treepath][0] = True
    def _on_calc(self, button):
        R1 = float(self._ph1_aperture_entry.get_active_text()) * 0.0005
        R2 = float(self._ph2_aperture_entry.get_active_text()) * 0.0005
        L1_elements = [float(x) for x in self._ph12_dist_elements_entry.get_selected()]
        L1 = sum(L1_elements) + 4 * len(L1_elements) + 4 + 100
        L2_elements = [float(x) for x in self._ph23_dist_elements_entry.get_selected()]
        L2 = sum(L2_elements) + 4 * len(L2_elements) + 4 + 100
        sddist = self._sddist[self._sddist_entry.get_active_text()]
        deltaL = self._p3_sample_dist_entry.get_value()
        deltaLprime = self._bs_det_dist_entry.get_value()
        L3 = sddist + deltaL
        if self._ph3_manual_selector.get_active():
            R3_geo = float(self._ph3_aperture_entry.get_active_text()) * 0.0005
        else:
            R3_geo = calc_R3_geo(R1, R2, L1, L2)
        BSradius_geo = calc_Delta_geo(R1, R2, R3_geo, L1, L2, L3)
        BSshadowradius_geo = calc_Delta_geo(R1, R2, R3_geo, L1, L2, L3 + deltaLprime)
        Rsample_geo = calc_Rsample_geo(R1, R2, L1, L2, deltaL)
        alpha_geo = calc_alpha_geo(R1, R2, L1) * 1e3
        beta_geo = calc_beta_geo(R2, R3_geo, L2) * 1e3
        qmin = 4 * np.pi * np.sin(0.5 * np.arctan(BSshadowradius_geo / sddist)) / 0.15418
        dmax = 2 * np.pi / qmin
        phi = 1 - 2 * R2 * L3 / (L1 + L2 + L3) / (R1 + R2)
        L1_opt = (L1 + L2) * (1 - (1 - phi) ** 0.5) / phi
        init_parameters = OrderedDict([('L1', L1), ('L2', L2), ('L3', L3), ('sddist', sddist), ('deltaL', deltaL), ('deltaLprime', deltaLprime)])
        results_GEO = OrderedDict([('R3_radius', R3_geo),
                                   ('sample_radius', Rsample_geo),
                                   ('beamstop_radius', BSradius_geo),
                                   ('detector_radius', BSshadowradius_geo),
                                   ('alpha', alpha_geo), ('beta', beta_geo), ('qmin', qmin), ('dmax', dmax),
                                   ('L1_opt', L1_opt), ('L2_opt', L1 + L2 - L1_opt)])
        results_MC = Pinhole_MonteCarlo(R1, R2, R3_geo, L1, L2, L3, deltaL, deltaLprime, BSradius_geo,
                                     self._Nrays_entry.get_value_as_int(),
                                     self._beamwidth_entry.get_value(),
                                     self._beamheight_entry.get_value(),
                                     self._beamdiv_entry.get_value() * 1e-3)
        results_MC['qmin_max'] = 4 * np.pi * np.sin(0.5 * np.arctan(results_MC['detector_max_radius'] / sddist)) / 0.15418
        results_MC['qmin_mean'] = 4 * np.pi * np.sin(0.5 * np.arctan(results_MC['detector_mean_radius'] / sddist)) / 0.15418
        results_MC['dmax_min'] = 2 * np.pi / results_MC['qmin_max']
        results_MC['dmax_mean'] = 2 * np.pi / results_MC['qmin_mean']
        results = init_parameters
        results.update(results_GEO)
        results.update(results_MC)
        self._results_model.clear()
        resultstrings = []
        for r in results:
            if r.startswith('_'):
                continue
            if r.startswith('R') and r.endswith('_radius'):
                name = 'PH' + r[1:].rsplit('_', 1)[0] + '_diameter'
                value = str(results[r] * 2000) + ' um'
            elif r.endswith('_radius'):
                name = r[0:].rsplit('_', 1)[0] + '_diameter'
                value = str(results[r] * 2) + ' mm'
            else:
                name = r
                value = str(results[r])
            self._results_model.append((False, name, value))
        self._last_results = results
        self._beampathlength_scale.set_range(-1, L1 + L2 + L3)
        self._beampathlength_scale.clear_marks()
        self._beampathlength_scale.add_mark(0, Gtk.PositionType.BOTTOM, 'PH#1')
        self._beampathlength_scale.add_mark(L1, Gtk.PositionType.TOP, 'PH#2')
        self._beampathlength_scale.add_mark(L1 + L2, Gtk.PositionType.BOTTOM, 'PH#3')
        self._beampathlength_scale.add_mark(L1 + L2 + deltaL, Gtk.PositionType.TOP, 'Sample')
        self._beampathlength_scale.add_mark(L1 + L2 + L3 - deltaLprime, Gtk.PositionType.BOTTOM, 'BS')
        self._beampathlength_scale.add_mark(L1 + L2 + L3, Gtk.PositionType.TOP, 'Det')
        self._beampathlength_scale.set_increments(1, 10)
        self._beampathlength_scale.set_value(-1)
