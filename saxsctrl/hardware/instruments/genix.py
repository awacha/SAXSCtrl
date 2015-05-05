"""genix.py

Interface to the GeniX3D (TM) X-ray beam delivery system by Xenocs.

Author: Andras Wacha (awacha@gmail.com)
Created: 21.01.2013.

Disclaimer: The author hereby denies all liability for damages resulting from using this software.
    Use this piece of code on your own risk. The author is not associated in any way with Xenocs SA.

--------
WARNING!
--------
Though this software has been written with greatest care, according to the official documentation by
Xenocs (GeniX3D - Installation and operation manual, version E, date 26/07/12), the possibility of
mistypes and coding failures cannot be excluded. Use this at your own risk, especially the functions
for setting the high tension and current of the tube. Before using them, please read through well the
official documentation. Especially that part concerning reducing the high tension to zero while the
current is finite, as this operation WILL DAMAGE THE POWER SOURCE!!! Be warned.
"""

import multiprocessing
import logging
import time
import itertools
from .instrument import InstrumentError, Instrument_ModbusTCP, InstrumentStatus, InstrumentProperty, InstrumentPropertyCategory
from gi.repository import Notify, GObject
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GenixStatus(InstrumentStatus):
    PowerDown = 'powered down'
    Standby = 'low power'
    FullPower = 'full power'
    WarmUp = 'warming up'
    GoPowerDown = 'powering down'
    GoStandby = 'going to low power'
    GoFullPower = 'going to full power'
    XRaysOff = 'X-rays off'


class ShutterStatus(object):
    Open = 'open'
    Closed = 'closed'
    Moving = 'moving'
    Disconnected = 'disconnected'


class GenixError(InstrumentError):
    pass


class LoggingLock(object):

    def __init__(self, name, loglevel=logging.DEBUG):
        self.lock = multiprocessing.Lock()
        self.name = name
        self.loglevel = loglevel
        self.lockstate = False

    def acquire(self, *args, **kwargs):
        logger.log(self.loglevel, 'Acquiring lock: ' + self.name +
                   'State before: ' + str(self.lockstate))
        logger.log(self.loglevel, 'Lock is: ' + self.name + str())
        res = self.lock.acquire(*args, **kwargs)
        self.lockstate = True
        logger.log(self.loglevel, 'Acquired lock: ' + self.name)
        return res

    def release(self, *args, **kwargs):
        logger.log(self.loglevel, 'Releasing lock: ' + self.name +
                   'State before: ' + str(self.lockstate))
        res = self.lock.release(*args, **kwargs)
        self.lockstate = False
        logger.log(self.loglevel, 'Released lock: ' + self.name)
        return res

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type_, value, traceback):
        return self.release()


class Genix(Instrument_ModbusTCP):
    __gtype_name__ = 'SAXSCtrl_Instrument_GeniX'
    __gsignals__ = {'shutter': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),  # emitted when the shutter is opened or closed
                    }
    _shutter_timeout = 2
    _prevstate = GenixStatus.Idle
    _considered_idle = [GenixStatus.Disconnected, GenixStatus.FullPower,
                        GenixStatus.Standby, GenixStatus.PowerDown, GenixStatus.XRaysOff, GenixStatus.Idle]
    ht = InstrumentProperty(
        name='ht', type=float, refreshinterval=1, timeout=1)
    current = InstrumentProperty(
        name='current', type=float, refreshinterval=1, timeout=1)
    power = InstrumentProperty(
        name='power', type=float, refreshinterval=1, timeout=1)
    remote_mode = InstrumentProperty(
        name='remote_mode', type=bool, refreshinterval=1, timeout=1)
    xrays = InstrumentProperty(
        name='xrays', type=bool, refreshinterval=1, timeout=1)
    shutter = InstrumentProperty(
        name='shutter', type=bool, refreshinterval=1, timeout=1)
    tubetime = InstrumentProperty(
        name='tubetime', type=int, refreshinterval=1, timeout=1)
    conditions_auto = InstrumentProperty(
        name='conditions_auto', type=bool, refreshinterval=1, timeout=1)
    faults = InstrumentProperty(
        name='faults', type=bool, refreshinterval=1, timeout=1)
    xray_light_fault = InstrumentProperty(
        name='xray_light_fault', type=bool, refreshinterval=1, timeout=1)
    shutter_light_fault = InstrumentProperty(
        name='shutter_light_fault', type=bool, refreshinterval=1, timeout=1)
    sensor2_fault = InstrumentProperty(
        name='sensor2_fault', type=bool, refreshinterval=1, timeout=1)
    tube_position_fault = InstrumentProperty(
        name='tube_position_fault', type=bool, refreshinterval=1, timeout=1)
    vacuum_fault = InstrumentProperty(
        name='vacuum_fault', type=bool, refreshinterval=1, timeout=1)
    waterflow_fault = InstrumentProperty(
        name='waterflow_fault', type=bool, refreshinterval=1, timeout=1)
    safety_shutter_fault = InstrumentProperty(
        name='safety_shutter_fault', type=bool, refreshinterval=1, timeout=1)
    temperature_fault = InstrumentProperty(
        name='temperature_fault', type=bool, refreshinterval=1, timeout=1)
    sensor1_fault = InstrumentProperty(
        name='sensor1_fault', type=bool, refreshinterval=1, timeout=1)
    relay_interlock_fault = InstrumentProperty(
        name='relay_interlock_fault', type=bool, refreshinterval=1, timeout=1)
    door_fault = InstrumentProperty(
        name='door_fault', type=bool, refreshinterval=1, timeout=1)
    filament_fault = InstrumentProperty(
        name='filament_fault', type=bool, refreshinterval=1, timeout=1)
    tube_warmup_needed = InstrumentProperty(
        name='tube_warmup_needed', type=bool, refreshinterval=1, timeout=1)
    interlock = InstrumentProperty(
        name='interlock', type=bool, refreshinterval=1, timeout=1)
    overridden = InstrumentProperty(
        name='overridden', type=bool, refreshinterval=1, timeout=1)
    faultstatus = InstrumentProperty(
        name='faultstatus', type=int, refreshinterval=1, timeout=1)

    def __init__(self, name='source', offline=True):
        if self._OWG_nosave_props is None:
            self._OWG_nosave_props = []
        Instrument_ModbusTCP.__init__(self, name, offline)
        self._shutter_lock = multiprocessing.RLock()
        self.logfile = 'log.genix'
        self.logtimeout = 1
        self._logging_parameters = [
            ('ht', 'f4', '%.2f'), ('current', 'f4', '%.2f'), ('shutter', 'i', '%d'), ('faultstatus', 'i', '%d')]

    def _update_instrumentproperties(self, propertyname=None):
        try:
            statusbits = self.get_status_bits()
            status = self.get_status(statusbits)
        except InstrumentError as ie:
            logger.warn(
                'InstrumentError while getting status bits from GeniX: ' + traceback.format_exc())
            for propname in self._get_instrumentproperties():
                getattr(type(self), propname)._update(
                    self, None, InstrumentPropertyCategory.UNKNOWN)
            return
        if (propertyname is None) or (propertyname == 'shutter'):
            if status['SHUTTER_CLOSED'] and not status['SHUTTER_OPENED']:
                needs_emit = (('shutter' not in self._instrumentproperties) or
                              (self._instrumentproperties['shutter'] is None) or
                              (self._instrumentproperties['shutter'][0]))
                type(self).shutter._update(
                    self, False, InstrumentPropertyCategory.NO)
                if needs_emit:
                    self.emit('shutter', False)
            elif status['SHUTTER_OPENED'] and not status['SHUTTER_CLOSED']:
                needs_emit = (('shutter' not in self._instrumentproperties) or
                              (self._instrumentproperties['shutter'] is None) or
                              (not self._instrumentproperties['shutter'][0]))
                type(self).shutter._update(
                    self, True, InstrumentPropertyCategory.YES)
                if needs_emit:
                    self.emit('shutter', True)
        if (propertyname is None) or (propertyname == 'xrays'):
            if status['XRAY_ON']:
                type(self).xrays._update(
                    self, True, InstrumentPropertyCategory.YES)
            else:
                type(self).xrays._update(
                    self, False, InstrumentPropertyCategory.NO)
            return True
        try:
            ht = self.get_ht()
            current = self.get_current()
            if status['CYCLE_RESET_ON']:
                newstate = GenixStatus.GoPowerDown
            elif status['CYCLE_AUTO_ON']:
                newstate = GenixStatus.GoFullPower
            elif status['STANDBY_ON']:
                newstate = GenixStatus.GoStandby
            elif status['CYCLE_TUBE_WARM_UP_ON']:
                newstate = GenixStatus.WarmUp
            else:
                if ht == 0 and current == 0:
                    newstate = GenixStatus.PowerDown
                elif ht == 30 and current == 0.3:
                    newstate = GenixStatus.Standby
                elif ht == 50 and current == 0.6:
                    newstate = GenixStatus.FullPower
                else:
                    newstate = self.status
            self._threadsafe_set_property('status', newstate)
        except InstrumentError:
            logger.warn(
                'InstrumentError while getting HV and current from GeniX: ' + traceback.format_exc())
            for propname in self._get_instrumentproperties():
                getattr(type(self), propname)._update(
                    self, None, InstrumentPropertyCategory.UNKNOWN)
            return
        faultint = 0
        for faultproperty, faultkey, index in itertools.imap(lambda a, b: a + (b,), [('faults', 'FAULTS'), ('xray_light_fault', 'X-RAY_LIGHT_FAULT'),
                                                                                     (
                                                                                         'shutter_light_fault', 'SHUTTER_LIGHT_FAULT'),
                                                                                     ('sensor2_fault', 'SENSOR2_FAULT'), (
                                                                                         'tube_position_fault', 'TUBE_POSITION_FAULT'),
                                                                                     ('vacuum_fault', 'VACUUM_FAULT'), (
                                                                                         'waterflow_fault', 'WATERFLOW_FAULT'),
                                                                                     (
                                                                                         'safety_shutter_fault', 'SAFETY_SHUTTER_FAULT'),
                                                                                     (
                                                                                         'temperature_fault', 'TEMPERATURE_FAULT'),
                                                                                     (
                                                                                         'sensor1_fault', 'SENSOR1_FAULT'),
                                                                                     (
                                                                                         'relay_interlock_fault', 'RELAY_INTERLOCK_FAULT'),
                                                                                     (
                                                                                         'door_fault', 'DOOR_SENSOR_FAULT'),
                                                                                     (
                                                                                         'filament_fault', 'FILAMENT_FAULT'),
                                                                                     ('tube_warmup_needed', 'TUBE_WARM_UP_NEEDED_FAULT')], itertools.count(0)):
            if status[faultkey]:
                getattr(type(self), faultproperty)._update(
                    self, status[faultkey], InstrumentPropertyCategory.ERROR)
            else:
                getattr(type(self), faultproperty)._update(
                    self, status[faultkey], InstrumentPropertyCategory.OK)
            faultint += int(status[faultkey]) << index
        type(self).faultstatus._update(
            self, faultint, InstrumentPropertyCategory.NORMAL)
        type(self).ht._update(self, ht, InstrumentPropertyCategory.NORMAL)
        type(self).current._update(
            self, current, InstrumentPropertyCategory.NORMAL)
        type(self).power._update(
            self, ht * current, InstrumentPropertyCategory.NORMAL)
        type(self).tubetime._update(
            self, self.get_tube_time(), InstrumentPropertyCategory.NORMAL)
        for propname, key in [('interlock', 'INTERLOCK_OK'), ('conditions_auto', 'CONDITIONS_AUTO_OK'), ('xrays', 'XRAY_ON'),
                              ('remote_mode', 'DISTANT_MODE')]:
            if status[key]:
                getattr(type(self), propname)._update(
                    self, True, InstrumentPropertyCategory.YES)
            else:
                getattr(type(self), propname)._update(
                    self, False, InstrumentPropertyCategory.NO)
        for propname, key in [('overridden', 'OVERRIDDEN_ON')]:
            if status[key]:
                getattr(type(self), propname)._update(
                    self, True, InstrumentPropertyCategory.NO)
            else:
                getattr(type(self), propname)._update(
                    self, False, InstrumentPropertyCategory.YES)

    def do_notify(self, prop):
        Instrument_ModbusTCP.do_notify(self, prop)
        logger.info('GeniX status changed to: ' + self.status)
        if Notify.is_initted():
            n = Notify.Notification.new(
                'GeniX status change', 'New status: ' + self.status, 'dialog-information')
            n.show()
            del n

    def _pre_disconnect(self, should_do_communication):
        if should_do_communication:
            self.shutter_close(False)

    def get_status_bits(self):
        """Read the status bits of GeniX.
        """
        tup = self._read_coils(210, 36)
        # tup[26] closed
        # tup[27] opened
        return tup

    def get_status_int(self, tup=None):
        """Read the status bits of GeniX and return an integer from it."""
        if tup is None:
            tup = self.get_status_bits()
        return int(''.join([str(x) for x in tup]), base=2)

    def get_status(self, tup=None):
        """Read the status bits of GeniX and return a dict() of them.

        The meanings of the bits (dictionary items):
        --------------------------------------------
            DISTANT_MODE: Genix is in remote-controllable mode
            XRAY_ON: if X-rays are ON (key turned to ON position; can be disabled programmatically)
            STANDBY_ON: if the equipment is in low-power standby state
            CYCLE_AUTO_ON: if an automatic cycle is running
            CONDITIONS_AUTO_OK: if the conditions of running an automatic cycle are fulfilled
            CYCLE_RESET_ON: if a power-down operation is running
            CYCLE_TUBE_WARM_UP_ON: if a warm-up procedure is going on
            CONFIGURATION_POWER_TUBE: the rated power of the tube (1=50 W, 0=30W)
            FAULTS: if some fault conditions are present
            X-RAY_LIGHT_FAULT: if the X-rays ON light (orange) does not work
            SHUTTER_LIGHT_FAULT: if the shutter open light (red) does not work
            SENSOR2_FAULT: ???
            TUBE_POSITION_FAULT: if no X-ray tube is in place
            VACUUM_FAULT: if the optics is not evacuated
            WATERFLOW_FAULT: if the cooling water is not circulating
            SAFETY_SHUTTER_FAULT: fault of the safety beam shutter
            TEMPERATURE_FAULT: temperature of the X-ray tube is too high
            SENSOR1_FAULT: ???
            RELAY_INTERLOCK_FAULT: if the interlock is broken
            DOOR_SENSOR_FAULT: if the enclosure door is open
            FILAMENT_FAULT: X-ray tube filament broken
            TUBE_WARM_UP_NEEDED_FAULT: if the instrument recommends running a warm-up cycle.
            RUN_AUTOMATE: a 1 second blink-blink
            INTERLOCK_OK: if the interlock is OK (shutter can be opened)
            SHUTTER_CLOSED: if the shutter is closed
            SHUTTER_OPENED: if the shutter is open
            OVERRIDDEN_ON: if the safety circuits are overridden (expert mode, set with the key at the back) 
        """
        if tup is None:
            tup = self.get_status_bits()
        #logger.debug('GeniX status: 0x' + hex(self.get_status_int(tup)))
        return dict(zip(('DISTANT_MODE', 'XRAY_ON', 'STANDBY_ON', 'CYCLE_AUTO_ON', 'CONDITIONS_AUTO_OK', 'CYCLE_RESET_ON', 'CYCLE_TUBE_WARM_UP_ON',
                         'CONFIGURATION_POWER_TUBE', 'UNKNOWN1', 'FAULTS', 'X-RAY_LIGHT_FAULT', 'SHUTTER_LIGHT_FAULT', 'SENSOR2_FAULT', 'TUBE_POSITION_FAULT',
                         'VACUUM_FAULT', 'WATERFLOW_FAULT', 'SAFETY_SHUTTER_FAULT', 'TEMPERATURE_FAULT', 'SENSOR1_FAULT', 'RELAY_INTERLOCK_FAULT',
                         'DOOR_SENSOR_FAULT', 'FILAMENT_FAULT', 'TUBE_WARM_UP_NEEDED_FAULT', 'UNKNOWN2', 'RUN_AUTOMATE', 'INTERLOCK_OK', 'SHUTTER_CLOSED',
                         'SHUTTER_OPENED', 'UNKNOWN3', 'OVERRIDDEN_ON'), self.get_status_bits()))

    def isremote(self):
        return self.get_status()['DISTANT_MODE']

    def shutter_open(self, wait_for_completion=True):
        logger.debug('Acquiring shutter lock.')
        with self._shutter_lock:
            logger.debug('Checking if we are in remote mode.')
            if not self.isremote():
                raise GenixError('Not in remote mode')
            logger.debug('Opening shutter.')
            self._write_coil(248, 0)
            self._write_coil(247, 1)
            self._write_coil(247, 0)
            if not wait_for_completion:
                return
            t = time.time()
            while (self.shutter_state(now=True) != True) and (time.time() - t) < self._shutter_timeout:
                pass
            if self.shutter_state():
                logger.debug('Shutter is open.')
            else:
                logger.error('Opening shutter timed out.')
                raise GenixError('Shutter timeout!')

    def shutter_close(self, wait_for_completion=True):
        with self._shutter_lock:
            if not self.isremote():
                raise GenixError('Not in remote mode')
            logger.debug('Closing shutter.')
            self._write_coil(247, 0)
            self._write_coil(248, 1)
            self._write_coil(248, 0)
            if not wait_for_completion:
                return
            t = time.time()
            while (self.shutter_state() != False) and (time.time() - t) < self._shutter_timeout:
                pass
            if not self.shutter_state():
                logger.debug('Shutter is closed.')
            else:
                logger.error('Closing shutter timed out.')
                raise GenixError('Shutter timeout!')

    def shutter_state(self, now=False):
        if now:
            self._update_instrumentproperties('shutter')
        return self.shutter

    def xrays_on(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Turning X-rays on.')
        self._write_coil(251, 1)

    def xrays_off(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Turning X-rays off.')
        self._write_coil(251, 0)

    def xrays_state(self, now=False):
        if now:
            self._update_instrumentproperties('xrays')
        return self.xrays

    def reset_faults(self):
        """Acknowledge all fault conditions"""
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Resetting faults.')
        self._write_coil(249, 1)
        self._update_instrumentproperties()

    def get_faults(self):
        """Give a list of active fault conditions. 
        """
        status = self.get_status()
        return [k for k in status if k.endswith('_FAULT') and status[k]]

    def get_tube_time(self):
        """Return tube run time in hours.
        """
        return (self._read_integer(55) / 60.0 + self._read_integer(56))

    def do_standby(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Going to standby mode.')
        self._write_coil(250, 1)

    def do_rampup(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Ramping up.')
        self._write_coil(250, 0)
        self._write_coil(252, 1)
        self._write_coil(252, 0)

    def do_poweroff(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Powering off.')
        self._write_coil(250, 0)
        self._write_coil(244, 1)
        self._write_coil(244, 0)

    def do_warmup(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Warm-up procedure started.')
        self._write_coil(250, 0)
        self._write_coil(245, 1)
        self._write_coil(245, 0)

    def stop_warmup(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Stopping warm-up procedure.')
        self._write_coil(250, 0)
        self._write_coil(246, 1)
        self._write_coil(246, 0)
        self.do_poweroff()

    def get_ht(self):
        return self._read_integer(50) / 100.

    def get_current(self):
        return self._read_integer(51) / 100.

    def increase_ht(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Increasing high tension.')
        self._write_coil(242, 1)
        self._write_coil(242, 0)

    def decrease_ht(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Decreasing high tension.')
        self._write_coil(243, 1)
        self._write_coil(243, 0)

    def increase_current(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Increasing current.')
        self._write_coil(240, 1)
        self._write_coil(240, 0)

    def decrease_current(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Decreasing current.')
        self._write_coil(241, 1)
        self._write_coil(241, 0)

    def set_ht(self, ht):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Setting high tension to %.2f kV.' % ht)
        self._write_integer(252, ht * 10)

    def set_current(self, current):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.debug('Setting current to %.2f mA.' % current)
        self._write_integer(252, current * 100)

    def whichstate(self, status=None, ht=None, curr=None):
        if status is None:
            status = self.get_status()
        if not status['XRAY_ON']:
            return GenixStatus.XRaysOff
        if status['CYCLE_RESET_ON']:
            return GenixStatus.GoPowerDown
        elif status['CYCLE_AUTO_ON']:
            return GenixStatus.GoFullPower
        elif status['STANDBY_ON']:
            return GenixStatus.GoStandby
        elif status['CYCLE_TUBE_WARM_UP_ON']:
            return GenixStatus.WarmUp
        if ht is None:
            ht = self.get_ht()
        if curr is None:
            curr = self.get_current()
        if ht == 0 and curr == 0:
            return GenixStatus.PowerDown
        elif ht == 30 and curr == 0.3:
            return GenixStatus.Standby
        elif ht == 50 and curr == 0.6:
            return GenixStatus.FullPower
        else:
            return self.status

    def get_current_parameters(self):
        return {'HT': self.get_instrument_property('ht')[0],
                'Current': self.get_instrument_property('current')[0],
                'TubeTime': self.get_instrument_property('tubetime')[0],
                'Status': self.get_instrument_property('faultstatus')[0]}
