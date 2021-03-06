import logging
import os
import ConfigParser
import traceback
from .subsystem import SubSystem, SubSystemError
from ..instruments.pilatus import Pilatus
from ..instruments.genix import Genix
from ..instruments.tmcl_motor import TMCM351, TMCM6110
from ..instruments.vacgauge import VacuumGauge
from ..instruments.instrument import InstrumentError
from ..instruments.haakephoenix import HaakePhoenix
from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GLib
__all__ = ['SubSystemEquipments']

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SubSystemEquipments(SubSystem):
    __gsignals__ = {'equipment-connection': (GObject.SignalFlags.RUN_FIRST, None, (object, bool, bool)),
                    # equipment-connection is emitted whenever an equipment is connected or disconnected.
                    # the object argument is the equipment instance, the second argument is True for connect, False for disconnect
                    # and the third argument is True for normal disconnect,
                    # False for abnormal. For connection it is not significant.
                    # emitted whenever all connected equipments become idle
                    # after at least one of them was busy.
                    'idle': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    }
    __equipments__ = {'genix': Genix,
                      'pilatus': Pilatus,
                      'tmcm351_a': TMCM351,
                      'tmcm6110': TMCM6110,
                      'tmcm351_b': TMCM351,
                      'vacgauge': VacuumGauge,
                      'haakephoenix': HaakePhoenix,
                      }
    _motor_drivers = ['tmcm351_a', 'tmcm6110', 'tmcm351_b']

    def __init__(self, credo, offline=True):
        SubSystem.__init__(self, credo, offline)
        if not self.configfile:
            self.configfile = 'equipments.conf'
        self._list = dict([(n, self.__equipments__[n](
            name=n, offline=self.offline)) for n in self.__equipments__])
        self._equipment_connections = {}
        for eq in self._list:
            equip = self._list[eq]
            self._equipment_connections[eq] = [
                equip.connect('connect-equipment', self._equipment_connect),
                equip.connect('disconnect-equipment',
                              self._equipment_disconnect),
                equip.connect('idle', self._equipment_idle)]

    def is_idle(self):
        return all(eq.is_idle() for eq in self)

    def known_equipments(self):
        return self.__equipments__.keys()

    def connected_equipments(self):
        return [e for e in self.known_equipments() if self.is_connected(e)]

    def wait_for_idle(self, equipment, alternative_breakfunction=lambda: False):
        eq = self.get(equipment)
        return eq.wait_for_idle(alternative_breakfunction)

    def wait_for_all_idle(self, alternative_breakfunction=lambda: False):
        while not (self.is_idle() or alternative_breakfunction()):
            for i in range(100):
                GLib.main_context_default().iteration(False)
                if not GLib.main_context_default().pending():
                    break
        return (not alternative_breakfunction())

    def has_equipment(self, equipment):
        return equipment.lower() in self._list

    def is_connected(self, equipment):
        return self.get(equipment).connected()

    def get(self, equipment):
        if not self.has_equipment(equipment):
            raise SubSystemError('Equipment %s not connected.' % equipment)
        else:
            return self._list[equipment.lower()]

    def get_motor_drivers(self):
        return [eq for eq in self.known_equipments() if eq in self._motor_drivers]

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
        except InstrumentError as exc:
            if not eq.connected():
                logger.error(
                    'Equipment not connected at the end of connection procedure: ' + equipment + '. Error: ' + traceback.format_exc())
                raise SubSystemError(
                    'Cannot connect to equipment: ' + traceback.format_exc())

    def _equipment_connect(self, equipmentinstance):
        try:
            equipment = [
                e for e in self._list.values() if e is equipmentinstance][0]
        except IndexError:
            raise NotImplementedError('Invalid equipment.')
        self.emit('equipment-connection', equipment, True, equipmentinstance)
        return False

    def _equipment_disconnect(self, equipmentinstance, status):
        try:
            equipment = [
                e for e in self._list.values() if e is equipmentinstance][0]
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
            raise SubSystemError(
                'Cannot connect to all instruments. Failed: ' + ', '.join(errors))

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

    def savestate(self, configparser, sectionprefix=''):
        if self.offline:
            logger.warning('Not saving equipments state: we are off-line')
            return
        SubSystem.savestate(self, configparser, sectionprefix)
        cp = ConfigParser.ConfigParser()
        cffn = os.path.join(
            self.credo().subsystems['Files'].configpath, self.configfile)
        cp.read(cffn)
        for eq in self:
            eq.savestate(cp)
        with open(cffn, 'wt') as f:
            cp.write(f)

    def loadstate(self, configparser, sectionprefix=''):
        SubSystem.loadstate(self, configparser, sectionprefix)
        cp = ConfigParser.ConfigParser()
        logger.debug('SubSystemEquipments.loadstate: ' + self.configfile)
        cffn = os.path.join(
            self.credo().subsystems['Files'].configpath, self.configfile)
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
            b.connect('clicked', lambda b, eq,
                      tab: self._setup_dialog_equipment(eq, tab), eqname, tab)
            grid.attach(b, i % 6, i / 6, 1, 1)
        return tab

    def _setup_dialog_equipment(self, eqname, tab):
        dia = self.get(eqname).create_setup_dialog(
            parent=tab.get_toplevel(),
            flags=Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL)
        while dia.run() in (Gtk.ResponseType.REJECT, Gtk.ResponseType.APPLY):
            pass
        dia.destroy()
        del dia
