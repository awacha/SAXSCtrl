import logging
import os
import ConfigParser
from .subsystem import SubSystem, SubSystemError
from ..instruments.pilatus import Pilatus
from ..instruments.genix import Genix
from ..instruments.tmcl_motor import TMCM351
from ..instruments.vacgauge import VacuumGauge
from ..instruments.instrument import InstrumentError
from gi.repository import Gtk
from gi.repository import GObject

__all__ = ['SubSystemEquipments']

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SubSystemEquipments(SubSystem):
    __gsignals__ = {'equipment-connection':(GObject.SignalFlags.RUN_FIRST, None, (object, bool, bool)),
                    # equipment-connection is emitted whenever an equipment is connected or disconnected.
                    # the object argument is the equipment instance, the second argument is True for connect, False for disconnect
                    # and the third argument is True for normal disconnect, False for abnormal. For connection it is not significant.
                    'idle':(GObject.SignalFlags.RUN_FIRST, None, ()),  # emitted whenever all connected equipments become idle after at least one of them was busy.
                   }
    __equipments__ = {'genix':Genix,
                      'pilatus':Pilatus,
                      'tmcm351':TMCM351,
                      'vacgauge':VacuumGauge,
#                      'haakephoenix':{'class':None, 'port':2002, 'connectfunc':'connect_to_controller', 'disconnectfunc':'disconnect_from_controller'},
                      }
    def __init__(self, credo):
        SubSystem.__init__(self, credo)
        if not self.configfile:
            self.configfile = 'equipments.conf'
        self._list = dict([(n, self.__equipments__[n]()) for n in self.__equipments__])
        self._equipment_connections = {}
        for eq in self._list:
            equip = self._list[eq]
            self._equipment_connections[eq] = [equip.connect('connect-equipment', self._equipment_connect),
                                               equip.connect('disconnect-equipment', self._equipment_disconnect),
                                               equip.connect('idle', self._equipment_idle)]
    def is_idle(self):
        return all(eq.is_idle() for eq in self)
    def known_equipments(self):
        return self.__equipments__.keys()
    def connected_equipments(self):
        return [e for e in self.known_equipments() if self.is_connected(e)]
    def wait_for_idle(self, equipment):
        eq = self.get(equipment)
        while not eq.is_idle():
            for i in range(100):
                GObject.main_context_default().iteration(False)
                if not GObject.main_context_default().pending():
                    break
    def wait_for_all_idle(self):
        while not self.is_idle():
            for i in range(100):
                GObject.main_context_default().iteration(False)
                if not GObject.main_context_default().pending():
                    break
    def has_equipment(self, equipment):
        return equipment.lower() in self._list
    def is_connected(self, equipment):
        return self.get(equipment).connected()
    def get(self, equipment):
        if not self.has_equipment(equipment):
            raise SubSystemError('Equipment %s not connected.' % equipment)
        else:
            return self._list[equipment.lower()]
    def _equipment_idle(self, equipment):
        # this is called if the 'idle' signal of an equipment is emitted.
        if self.is_idle():
            # if all equipments are idle, emit our idle signal.
            self.emit('idle')
    def __iter__(self):
        return self._list.itervalues()
    def disconnect_equipment(self, equipment):
        equipment = equipment.lower()
        if not self.has_equipment(equipment):
            raise NotImplementedError('Unknown equipment ' + equipment)
        logger.info('Disconnecting from equipment: ' + equipment)
        if self.get(equipment).connected():
            self.get(equipment).disconnect_from_controller(True)
    def connect_equipment(self, equipment, **kwargs):
        """Connect to an equipment. Supply connection parameters such as host, port etc.
        as keyword arguments. Befor calling connect_to_controller() on the equipment,
        its corresponding properties will be set."""
        equipment = equipment.lower()
        if not self.has_equipment(equipment):
            raise NotImplementedError('Unknown equipment ' + equipment)
        if self.is_connected(equipment):
            raise SubSystemError('Equipment %s already connected!' % equipment)
        eq = self.get(equipment)
        for k in kwargs:
            setattr(eq, k, kwargs[k])
        try:
            eq.connect_to_controller()
        except Exception as exc:
            if not eq.connected():
                logger.error('Equipment not connected at the end of connection procedure: ' + equipment + '. Error: ' + exc.message)
                raise SubSystemError('Cannot connect to equipment: ' + exc.message)
    def _equipment_connect(self, equipmentinstance):
        try:
            equipment = [e for e in self._list.values() if e is equipmentinstance][0]
        except IndexError:
            raise NotImplementedError('Invalid equipment.')
        self.emit('equipment-connection', equipment, True, equipmentinstance)
        return False
    def _equipment_disconnect(self, equipmentinstance, status):
        try:
            equipment = [e for e in self._list.values() if e is equipmentinstance][0]
        except IndexError:
            raise NotImplementedError('Invalid equipment.')
        self.emit('equipment-connection', equipment, False, equipmentinstance)
        return False
        
    def connect_to_all(self):
        errors = []
        for eq in self.__equipments__:
            try:
                self.connect_equipment(eq)
            except (InstrumentError, SubSystemError):
                errors.append(eq)
        if errors:
            raise SubSystemError('Cannot connect to all instruments. Failed: ' + ', '.join(errors))
    def disconnect_from_all(self):
        for eq in self._list.keys()[:]:
            if self.is_connected(eq):
                self.disconnect_equipment(eq)
    def destroy(self):
        self.disconnect_from_all()
    def get_current_parameters(self):
        dic = {}
        for eq in self:
            if eq.connected():
                dic.update(eq.get_current_parameters())
        return dic
    def savestate(self, configparser):
        SubSystem.savestate(self, configparser)
        cp = ConfigParser.ConfigParser()
        cffn = os.path.join(self.credo().subsystems['Files'].configpath, self.configfile)
        cp.read(cffn)
        for eq in self:
            eq.savestate(cp)
        with open(cffn, 'wt') as f:
            cp.write(f)
    def loadstate(self, configparser):
        SubSystem.loadstate(self, configparser)
        cp = ConfigParser.ConfigParser()
        logger.debug('SubSystemEquipments.loadstate: ' + self.configfile)
        cffn = os.path.join(self.credo().subsystems['Files'].configpath, self.configfile)
        cp.read(cffn)
        for eq in self:
            eq.loadstate(cp)
    def create_setup_table(self, homogeneous=False):
        tab = SubSystem.create_setup_table(self, homogeneous)
        row, ncols = tab.get_size()
        f = Gtk.Frame(label='Equipments:')
        tab.attach(f, 0, ncols, row, row + 1)
        grid = Gtk.Grid()
        f.add(grid)
        for i, eqname in enumerate(self.known_equipments()):
            b = Gtk.Button(label=eqname.capitalize())
            b.connect('clicked', lambda b, eq, tab: self._setup_dialog_equipment(eq, tab), eqname, tab)
            grid.attach(b, i % 6, i / 6, 1, 1)
        return tab
    def _setup_dialog_equipment(self, eqname, tab):
        dia = self.get(eqname).create_setup_dialog(parent=tab.get_toplevel(), flags=Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL)
        while dia.run() in (Gtk.ResponseType.REJECT, Gtk.ResponseType.APPLY):
            pass
        dia.destroy()
        del dia
