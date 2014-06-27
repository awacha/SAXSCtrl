from gi.repository import Gtk
from gi.repository import GObject
from .widgets import ToolDialog
import numpy as np

class Inventory(GObject.GObject):
    _items=None
    _grabbed=None
    __gsignals__ = {'items-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'grab-changed':(GObject.SignalFlags.RUN_FIRST, None, ())}
    def __init__(self, items=[]):
        GObject.GObject.__init__(self)
        self._items=dict()
        self._grabbed=dict()
        if isinstance(items,list):
            for i in items:
                self.add(i)
        elif isinstance(items,dict):
            for i in items:
                self.add(i,items[i])
    def add(self,item,multiplicity=1):
        if item not in self._items:
            self._items[item]=multiplicity
        else:
            self._items[item]+=multiplicity
        if item not in self._grabbed:
            self._grabbed[item]=0
        self.emit('items-changed')
    def remove(self, item, multiplicity=1):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        elif (self._items[item]-self._grabbed[item])<multiplicity:
            raise KeyError('Not enough free instances of item in inventory!')
        else:
            self._items[item]-=multiplicity
            if self._items[item]<1:
                del self._items[item]
                del self._grabbed[item]
            self.emit('items-changed')
    def grab(self, item, multiplicity=1):
        if item not in self._items:
            raise KeyError('Item %s not in inventory!'%item)
        if (self._items[item]-self._grabbed[item])<multiplicity:
            raise KeyError('Not enough free instances of this item to grab!')
        else:
            self._grabbed[item]+=1
        self.emit('grab-changed')
    def release(self, item, multiplicity=1):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        elif self._grabbed[item]<multiplicity:
            raise KeyError('Cannot release more instances than are currently grabbed!')
        else:
            self._grabbed[item]-=multiplicity
        self.emit('grab-changed')
    def get_items(self):
        return self._items.copy()
    def get_multiplicity(self,item):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        return self._items[item]
    def get_n_free(self,item):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        return self._items[item]-self._grabbed[item]
    def get_n_grabbed(self, item):
        if item not in self._items:
            raise KeyError('Item not in inventory!')
        return self._grabbed[item]
    
class InventorySelectorButtons(Gtk.Grid):
    ncolumns=GObject.property(type=int, minimum=1, default=5, blurb='Number of columns')
    _inventory=None
    def __init__(self, inventory):
        Gtk.Grid.__init__(self)
        self._inventory=inventory
        self._itembuttons=[]
        self._inventory.connect('items-changed',self._inventory_items_change)
        self._inventory.connect('grab-changed',self._inventory_grab_change)
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
                self._itembuttons[-1]._isconn=self._itembuttons[-1].connect('toggled', self._item_button_toggled)
                self.attach(self._itembuttons[-1],(len(self._itembuttons)-1) % self.ncolumns, (len(self._itembuttons)-1) / self.ncolumns, 1,1)
        self._adjust_grabs()
    def _item_button_toggled(self,button):
        if button.get_active():
            self._inventory.grab(button.get_label())
        else:
            self._inventory.release(button.get_label())

    def _adjust_grabs(self):
        for i in self._inventory.get_items():
            buttons=[b for b in self._itembuttons if b.get_label()==i]
            n_grabbed=self._inventory.get_n_grabbed(i)
            toggled_buttons=[b for b in buttons if b.get_active()]
            released_buttons=[b for b in buttons if not b.get_active()]
            n_to_be_grayed=n_grabbed-len(toggled_buttons)
            for b in toggled_buttons:
                b.set_sensitive(True)
            for idx,b in enumerate(reversed(released_buttons)):
                if idx<n_to_be_grayed:
                    b.set_sensitive(False)
                else:
                    b.set_sensitive(True)
            # we have len(buttons) buttons for this item. From these
        
    def do_notify(self, prop):
        if prop.name=='ncolumns':
            self._repopulate()
    def _inventory_grab_change(self, inventory):
        return self._adjust_grabs()
    def get_selected(self):
        return [b.get_label() for b in self._itembuttons if b.get_active()]

# radius of the third pin-hole, can be calculated from R1, R2, L1, L2. The criterion is that the 3rd pin-hole
# cuts away only the parasitic scattering from R2, but does not touch the photons, which are unaffected either by R1 or R2.
calc_R3_geo=lambda R1, R2, L1, L2: R2+L2*(R1+R2)/(L1*1.0)

# size of the beam-stop. The beam stop should cover the remaining parasitic scattering from R2.
calc_Delta_geo=lambda R1,R2,R3,L1,L2,L3: R3*(1+L3/float(L2))+R2*(L3/float(L2))

# effective (larger) size of the beam-stop at the detector surface
calc_Deltaprime_geo=lambda R1,R2,R3,L1,L2,L3, deltaLprime: R3*(1+(L3+deltaLprime)/float(L2))+R2*((L3+deltaLprime)/float(L2))

# radius of the beam at the sample position
calc_Rsample_geo=lambda R1,R2,L1,L2,deltaL: R2+(L2+deltaL)*(R1+R2)/float(L1)

# maximum divergence defined by the first two pin-holes
calc_alpha_geo=lambda R1, R2, L1: np.arctan((R1+R2)/L1)

# maximum divergence defined by the last two pin-holes
calc_beta_geo=lambda R2, R3, L2: np.arctan((R2+R3)/L2)

def Pinhole_MonteCarlo(R1, R2, R3, L1, L2, L3, deltaL, deltaLprime, BSsize, Nrays):
    pass
    
class PinHoleCalculator(ToolDialog):
    _pinhole_inventory=[150,150,200,300,300,400,400,400,500,500,500,600,600,750,750,750,1000,1000,1000,1250]
    _distelement_inventory=[100,100,200,200,500,800]
    _sddist={'Short tube':457.121,'Long tube':1200,'Both tubes':1494.336}
    _R3_to_sample=50+4+30+110
    _bsfront_to_detector=54
    def __init__(self, credo, title='Pin-hole calculator'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        self._distelement_inventory=Inventory([str(x) for x in self._distelement_inventory])
        self._pinhole_inventory=Inventory([str(x) for x in self._pinhole_inventory])
        
        vb = self.get_content_area()
        grid=Gtk.Grid()
        vb.pack_start(grid,True,True,0)
        row=0
        l=Gtk.Label(label='Pin-hole #1 diameter (um):')
        l.set_alignment(0,0.5)
        grid.attach(l,0,row,1,1)
        l.set_hexpand(False)
        self._ph1_aperture_entry=Gtk.ComboBoxText()
        for phdiam in sorted(self._pinhole_inventory.get_items(),key=lambda x:float(x)):
            self._ph1_aperture_entry.append_text(phdiam)
        self._ph1_aperture_entry.set_active(0)
        grid.attach(self._ph1_aperture_entry,1,row,1,1)
        row+=1
        l=Gtk.Label(label='Pin-hole #2 diameter (um):')
        l.set_alignment(0,0.5)
        grid.attach(l,0,row,1,1)
        l.set_hexpand(False)
        self._ph2_aperture_entry=Gtk.ComboBoxText()
        for phdiam in sorted(self._pinhole_inventory.get_items(),key=lambda x:float(x)):
            self._ph2_aperture_entry.append_text(phdiam)
        self._ph2_aperture_entry.set_active(0)
        grid.attach(self._ph2_aperture_entry,1,row,1,1)
        row+=1
        self._ph3_manual_selector=Gtk.CheckButton(label='Pin-hole #3 diameter (um):')
        self._ph3_manual_selector.set_alignment(0,0.5)
        grid.attach(self._ph3_manual_selector,0,row,1,1)
        self._ph3_manual_selector.set_hexpand(False)
        self._ph3_aperture_entry=Gtk.ComboBoxText()
        for phdiam in sorted(self._pinhole_inventory.get_items(),key=lambda x:float(x)):
            self._ph3_aperture_entry.append_text(phdiam)
        grid.attach(self._ph3_aperture_entry,1,row,1,1)
        self._ph3_manual_selector.connect('toggled',lambda button, combo: combo.set_sensitive(button.get_active()),self._ph3_aperture_entry)
        self._ph3_aperture_entry.set_sensitive(False)
        self._ph3_manual_selector.set_active(False)
        row+=1
        self._bs_manual_selector=Gtk.CheckButton(label='Beamstop diameter (mm):')
        self._bs_manual_selector.set_alignment(0,0.5)
        grid.attach(self._bs_manual_selector,0,row,1,1)
        self._bs_manual_selector.set_hexpand(False)
        self._bs_size_entry=Gtk.SpinButton(digits=2)
        grid.attach(self._bs_size_entry,1,row,1,1)
        self._bs_size_entry.set_range(0,10000)
        self._bs_size_entry.set_increments(1,10)
        self._bs_size_entry.set_value(4)
        self._bs_manual_selector.connect('toggled',lambda button, combo: combo.set_sensitive(button.get_active()),self._bs_size_entry)
        self._bs_size_entry.set_sensitive(False)
        self._bs_manual_selector.set_active(False)
        row+=1
        l=Gtk.Label(label='Pin-hole #1-#2 distance elements:')
        l.set_alignment(0,0.5)
        grid.attach(l,0,row,1,1)
        l.set_hexpand(False)
        self._ph12_dist_elements_entry=InventorySelectorButtons(self._distelement_inventory)
        grid.attach(self._ph12_dist_elements_entry,1,row,1,1)
        row+=1
        l=Gtk.Label(label='Pin-hole #2-#3 distance elements:')
        l.set_alignment(0,0.5)
        grid.attach(l,0,row,1,1)
        l.set_hexpand(False)
        self._ph23_dist_elements_entry=InventorySelectorButtons(self._distelement_inventory)
        grid.attach(self._ph23_dist_elements_entry,1,row,1,1)
        row+=1
        
        l=Gtk.Label(label='Sample-to-detector distance (mm):')
        l.set_alignment(0,0.5)
        grid.attach(l,0,row,1,1)
        l.set_hexpand(False)
        self._sddist_entry=Gtk.ComboBoxText()
        for sdd in sorted(self._sddist):
            self._sddist_entry.append_text(sdd)
        self._sddist_entry.set_active(0)
        grid.attach(self._sddist_entry,1,row,1,1)
        row+=1
        
        l=Gtk.Label(label='Pin-hole #3-to-sample distance (mm):')
        l.set_alignment(0,0.5)
        grid.attach(l,0,row,1,1)
        l.set_hexpand(False)
        self._p3_sample_dist_entry=Gtk.SpinButton(digits=2)
        self._p3_sample_dist_entry.set_range(0,10000)
        self._p3_sample_dist_entry.set_increments(1,10)
        self._p3_sample_dist_entry.set_value(self._R3_to_sample)
        grid.attach(self._p3_sample_dist_entry,1,row,1,1)
        row+=1
        
        l=Gtk.Label(label='Beamstop front-to-detector distance (mm):')
        l.set_alignment(0,0.5)
        grid.attach(l,0,row,1,1)
        l.set_hexpand(False)
        self._bs_det_dist_entry=Gtk.SpinButton(digits=2)
        self._bs_det_dist_entry.set_range(0,10000)
        self._bs_det_dist_entry.set_increments(1,10)
        self._bs_det_dist_entry.set_value(self._bsfront_to_detector)
        grid.attach(self._bs_det_dist_entry,1,row,1,1)
        row+=1

        self._calc_button=Gtk.Button.new_from_icon_name('accessories-calculator',Gtk.IconSize.BUTTON)
        self._calc_button.set_label('Calculate')
        self._calc_button.connect('clicked',self._on_calc)
        grid.attach(self._calc_button,0,row,2,1)
        row+=1
        f=Gtk.Frame(label='Results')
        f.set_vexpand(True)
        grid.attach(f,0,row,2,1)       
        self._results_label=Gtk.Label()
        f.add(self._results_label)
        self.show_all()
    def _on_calc(self,button):
        R1=float(self._ph1_aperture_entry.get_active_text())*0.0005
        R2=float(self._ph2_aperture_entry.get_active_text())*0.0005
        L1_elements=[float(x) for x in self._ph12_dist_elements_entry.get_selected()]
        L1=sum(L1_elements)+4*len(L1_elements)+4+100
        L2_elements=[float(x) for x in self._ph23_dist_elements_entry.get_selected()]
        L2=sum(L2_elements)+4*len(L2_elements)+4+100
        sddist=self._sddist[self._sddist_entry.get_active_text()]
        deltaL=self._p3_sample_dist_entry.get_value()
        deltaLprime=self._bs_det_dist_entry.get_value()
        L3=sddist+deltaL
        if self._ph3_manual_selector.get_active():
            R3_geo=float(self._ph3_aperture_entry.get_active_text())*0.0005
        else:
            R3_geo=calc_R3_geo(R1,R2,L1,L2)
        if self._bs_manual_selector.get_active():
            raise NotImplementedError("This is not yet correct! BSshadowradius should be calculated correctly. ")
            BSradius_geo=float(self._bs_size_entry.get_value())*0.5
        else:
            BSradius_geo=calc_Delta_geo(R1,R2,R3_geo,L1,L2,L3)
        BSshadowradius_geo=calc_Delta_geo(R1,R2,R3_geo,L1,L2,L3+deltaLprime)
        Rsample_geo=calc_Rsample_geo(R1,R2,L1,L2,deltaL)
        alpha_geo=calc_alpha_geo(R1,R2,L1)
        beta_geo=calc_beta_geo(R2,R3_geo,L2)
        qmin=4*np.pi*np.sin(0.5*np.arctan(BSshadowradius_geo/sddist))/0.15418
        dmax=2*np.pi/qmin
        phi=1-2*R2*L3/(L1+L2+L3)/(R1+R2)
        L1_opt=(L1+L2)*(1-(1-phi)**0.5)/phi
        resultstring="""
        Distance between PH1-PH2: %g mm
        Distance between PH2-PH3: %g mm
        Distance between PH3-Det: %g mm
        PH1 diameter: %g um
        PH2 diameter: %g um
        PH3 diameter: %g um
        Beam stop diameter: %g mm
        Beam stop shadow on detector: %g mm
        Beam diameter at sample: %g mm
        Max divergence given by PH1-PH2: %g mrad
        Max divergence given by PH2-PH3: %g mrad
        Q_min: %g nm-1
        D_max: %g nm
        Optimal division of PH1-PH3 distance would be: %g and %g mm.
        """%(L1, L2, L3, R1*2000,R2*2000,R3_geo*2000,BSradius_geo*2,BSshadowradius_geo*2,Rsample_geo*2,alpha_geo*1e3,beta_geo*1e3,qmin,dmax,L1_opt,L1+L2-L1_opt)
        self._results_label.set_label(resultstring)