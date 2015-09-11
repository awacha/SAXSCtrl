from .subsystem import SubSystem, SubSystemError
from gi.repository import GObject
from gi.repository import GLib
import weakref
import logging
import traceback
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SubSystemMotors(SubSystem):
    __gsignals__ = {'motors-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    'motor-start': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'motor-report': (GObject.SignalFlags.RUN_FIRST, None, (object, float, float, float)),
                    'motor-stop': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'motor-limit': (GObject.SignalFlags.RUN_FIRST, None, (object, bool, bool)),
                    'motor-settings-changed': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'idle': (GObject.SignalFlags.RUN_FIRST, None, ()), }

    def __init__(self, credo, offline=True):
        SubSystem.__init__(self, credo, offline)
        self._conns = []
        self._driverconns = []
        for md in [self.credo().get_equipment(md) for md in self.credo().subsystems['Equipments'].get_motor_drivers()]:
            for signame in ['motors-changed', 'motor-start', 'motor-report', 'motor-stop', 'motor-limit', 'motor-settings-changed']:
                self._conns.append(
                    (weakref.ref(md), md.connect(signame, self._proxy_signal, signame)))
                self._driverconns.append(
                    (md, md.connect('connect-equipment', self._on_driver_connect)))
                self._driverconns.append(
                    (md, md.connect('disconnect-equipment', self._on_driver_disconnect)))
                self._driverconns.append(
                    (md, md.connect('idle', self._on_driver_idle)))

    def __del__(self):
        for obj, conn in self._driverconns:
            obj.disconnect(conn)
        self._driverconns = []
        for obj, conn in self._conns:
            try:
                obj().disconnect(conn)
            except (weakref.ReferenceError, AttributeError):
                pass
        self._conns = []

    def _on_driver_connect(self, driver):
        self.emit('motors-changed')

    def _on_driver_disconnect(self, driver, status):
        self.emit('motors-changed')

    def _on_driver_idle(self, driver):
        if self.is_idle():
            self.emit('idle')

    def stop_all(self):
        for mot in self:
            mot.stop()

    def get_motors(self):
        mots = []
        for md in [dr for dr in self.credo().subsystems['Equipments'].get_motor_drivers() if self.credo().subsystems['Equipments'].is_connected(dr)]:
            mots.extend(
                list(self.credo().subsystems['Equipments'].get(md).motors.values()))
        return sorted(mots, key=lambda x: x.name)

    def _proxy_signal(self, *args):
        self.emit(args[-1], *(args[1:-1]))

    def get(self, motorname, casesensitive=True):
        mots = self.get_motors()
        lis = [m for m in mots if m.name == motorname or (
            (not casesensitive) and m.name.upper() == motorname.upper())]
        if len(lis) == 1:
            return lis[0]
        lis = [m for m in mots if m.alias == motorname or (
            (not casesensitive) and m.alias.upper() == motorname.upper())]
        if len(lis) == 1:
            return lis[0]
        lis = [m for m in mots if str(m) == motorname or (
            (not casesensitive) and str(m).upper() == motorname.upper())]
        if len(lis) == 1:
            return lis[0]
        raise SubSystemError('Cannot find motor: ' + str(motorname))

    def is_idle(self):
        return all([self.credo().subsystems['Equipments'].get(dr).is_idle() for dr in self.credo().subsystems['Equipments'].get_motor_drivers() if self.credo().subsystems['Equipments'].is_connected(dr)])

    def wait_for_idle(self, alternative_breakfunc=lambda: False):
        """Wait until the instrument becomes idle or alternative_breakfunc() returns True.
        During the wait, this calls the default GObject main loop.
        """
        while not (self.is_idle() or alternative_breakfunc()):
            for i in range(100):
                GLib.main_context_default().iteration(False)
                if not GLib.main_context_default().pending():
                    break
        return (not alternative_breakfunc())

    def __iter__(self):
        for m in self.get_motors():
            yield m
