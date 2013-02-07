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

import modbus_tk.modbus_tcp
import modbus_tk.defines
import threading
import logging
import time

logger = logging.getLogger(__name__)

class GenixError(StandardError):
    pass

class GenixConnection(object):
    error_handler = None
    _comm_lock = threading.Lock()
    _shutter_lock = threading.Lock()
    _shutter_timeout = 1
    def __init__(self, host, port=502):
        self.connection = modbus_tk.modbus_tcp.TcpMaster(host, port)
        self.connection.set_timeout(1)
        try:
            self.connection.open()
        except:
            raise GenixError('Cannot connect to GeniX at %s:%d' % (host, port))
    def _read_integer(self, regno):
        with self._comm_lock:
            try:
                return self.connection.execute(1, modbus_tk.defines.READ_INPUT_REGISTERS, regno, 1)[0]
            except:
                if hasattr(self.error_handler, '__call__'):
                    self.error_handler.__call__('error')
                raise GenixError('Communication error on reading integer value.')
    def _write_coil(self, coilno, val):
        with self._comm_lock:
            try:
                self.connection.execute(1, modbus_tk.defines.WRITE_SINGLE_COIL, coilno, 1, val)
            except:
                if hasattr(self.error_handler, '__call__'):
                    self.error_handler.__call__('error')
                raise GenixError('Communication error on writing coil.')
    def get_status_bits(self):
        """Read the status bits of GeniX.
        """
        with self._comm_lock:
            try:
                coils = self.connection.execute(1, modbus_tk.defines.READ_COILS, 210, 36)
            except:
                if hasattr(self.error_handler, '__call__'):
                    self.error_handler.__call__('error')
                raise GenixError('Communication error')
            return coils
    def get_status_int(self):
        """Read the status bits of GeniX and return an integer from it."""
        tup = self.get_status_bits()
        return int(''.join([str(x) for x in tup]), base=2)
    def get_status(self):
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
        return dict(zip(('DISTANT_MODE', 'XRAY_ON', 'STANDBY_ON', 'CYCLE_AUTO_ON', 'CONDITIONS_AUTO_OK', 'CYCLE_RESET_ON', 'CYCLE_TUBE_WARM_UP_ON',
                     'CONFIGURATION_POWER_TUBE', 'UNKNOWN1', 'FAULTS', 'X-RAY_LIGHT_FAULT', 'SHUTTER_LIGHT_FAULT', 'SENSOR2_FAULT', 'TUBE_POSITION_FAULT',
                     'VACUUM_FAULT', 'WATERFLOW_FAULT', 'SAFETY_SHUTTER_FAULT', 'TEMPERATURE_FAULT', 'SENSOR1_FAULT', 'RELAY_INTERLOCK_FAULT',
                     'DOOR_SENSOR_FAULT', 'FILAMENT_FAULT', 'TUBE_WARM_UP_NEEDED_FAULT', 'UNKNOWN2', 'RUN_AUTOMATE', 'INTERLOCK_OK', 'SHUTTER_CLOSED',
                     'SHUTTER_OPENED', 'UNKNOWN3', 'OVERRIDDEN_ON'), self.get_status_bits()))
    def isremote(self):
        return self.get_status()['DISTANT_MODE']
    def shutter_open(self, wait_for_completion=True):
        with self._shutter_lock:
            if not self.isremote():
                raise GenixError('Not in remote mode')
            logger.info('Opening shutter.')
            self._write_coil(248, 0)
            self._write_coil(247, 1)
            self._write_coil(247, 0)
            if not wait_for_completion:
                return
            t = time.time()
            while (self.shutter_state() != True) and (time.time() - t) < self._shutter_timeout:
                pass
            if self.shutter_state():
                logger.info('Shutter is open.')
            else:
                logger.error('Opening shutter timed out.')
                raise GenixError('Shutter timeout!')
    def shutter_close(self, wait_for_completion=True):
        with self._shutter_lock:
            if not self.isremote():
                raise GenixError('Not in remote mode')
            logger.info('Closing shutter.')
            self._write_coil(247, 0)
            self._write_coil(248, 1)
            self._write_coil(248, 0)
            if not wait_for_completion:
                return
            t = time.time()
            while (self.shutter_state() != False) and (time.time() - t) < self._shutter_timeout:
                pass
            if not self.shutter_state():
                logger.info('Shutter is closed.')
            else:
                logger.error('Closing shutter timed out.')
                raise GenixError('Shutter timeout!')
    def shutter_state(self):
        status = self.get_status()
        if status['SHUTTER_CLOSED'] and not status['SHUTTER_OPENED']:
            return False
        elif status['SHUTTER_OPENED'] and not status['SHUTTER_CLOSED']:
            return True
        else:
            return None
    def xrays_on(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Turning X-rays on.')
        self._write_coil(251, 1)
    def xrays_off(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Turning X-rays off.')
        self._write_coil(251, 0)
    def xrays_state(self):
        return self.get_status()['XRAY_ON']
    def reset_faults(self):
        """Acknowledge all fault conditions"""
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Resetting faults.')
        self._write_coil(249, 1)
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
        logger.info('Going to standby mode.')
        self._write_coil(250, 1)
    def do_rampup(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Ramping up.')
        self._write_coil(250, 0)
        self._write_coil(252, 1)
        self._write_coil(252, 0)
    def do_poweroff(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Powering off.')
        self._write_coil(250, 0)
        self._write_coil(244, 1)
        self._write_coil(244, 0)
    def do_warmup(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Warm-up procedure started.')
        self._write_coil(250, 0)
        self._write_coil(245, 1)
        self._write_coil(245, 0)
    def stop_warmup(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Stopping warm-up procedure.')
        self._write_coil(250, 0)
        self._write_coil(246, 1)
        self._write_coil(246, 0)
    def get_ht(self):
        return self._read_integer(50) / 100.
    def get_current(self):
        return self._read_integer(51) / 100.
    
    def increase_ht(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Increasing high tension.')
        self._write_coil(242, 1)
        self._write_coil(242, 0)
    def decrease_ht(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Decreasing high tension.')
        self._write_coil(243, 1)
        self._write_coil(243, 0)
    def increase_current(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Increasing current.')
        self._write_coil(240, 1)
        self._write_coil(240, 0)
    def decrease_current(self):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Decreasing current.')
        self._write_coil(241, 1)
        self._write_coil(241, 0)
    def set_ht(self, ht):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Setting high tension to %.2f kV.' % ht)
        self._write_integer(252, ht * 10)
    def set_current(self, current):
        if not self.isremote():
            raise GenixError('Not in remote mode')
        logger.info('Setting current to %.2f mA.' % current)
        self._write_integer(252, current * 100)
        
        
