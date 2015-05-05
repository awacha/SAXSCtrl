from .instrument import Instrument_TCP, InstrumentError, InstrumentStatus, Command, CommandReply, InstrumentProperty, InstrumentPropertyCategory, InstrumentPropertyUnknown
import dateutil.parser
import logging
import datetime
import threading
import math
import time
from gi.repository import GObject
from ...utils import objwithgui
import numpy as np
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TEMPERATURE_WARNING_LIMITS = [(20, 37), (20, 33), (20, 35)]
TEMPERATURE_ERROR_LIMITS = [(15, 55), (15, 35), (15, 45)]
HUMIDITY_WARNING_LIMITS = [45, 45, 10]
HUMIDITY_ERROR_LIMITS = [80, 80, 30]


RE_FLOAT = r"[+-]?(\d+)*\.?\d+([eE][+-]?\d+)?"
RE_DATE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+"
RE_INT = r"[+-]?\d+"


class CommandReplyPilatus(CommandReply):

    def __init__(self, context, regex, findall_regex=None, defaults=None):
        CommandReply.__init__(
            self, r'(?P<context>\d+)\s+(?P<status>[A-Z]+)\s+' + regex, findall_regex, defaults)
        self.context = context

    def match(self, message):
        gd = CommandReply.match(self, message)
        if (gd is not None) and int(gd['context']) != self.context:
            return None
        else:
            return gd

reply_noaccess = CommandReplyPilatus(1, r'access denied')


class PilatusError(InstrumentError):
    pass


class PilatusStatus(InstrumentStatus):
    Exposing = 'exposing'
    ExposingMulti = 'exposing multi'
    Trimming = 'trimming'


class Pilatus(Instrument_TCP):
    __gtype_name__ = 'SAXSCtrl_Instrument_Pilatus300k'
    _commands = [
        Command('Tau', [CommandReplyPilatus(15, r'Rate correction is on; tau = (?P<tau>' + RE_FLOAT + r') s, cutoff = (?P<cutoff>' + RE_INT + r') counts'),
                        CommandReplyPilatus(
                            15, r'Turn off rate correction', defaults={'tau': 0, 'cutoff': 1048574}),
                        CommandReplyPilatus(
                            15, r'Rate correction is off, cutoff = (?P<cutoff>' + RE_INT + r') counts', defaults={'tau': 0}),
                        CommandReplyPilatus(15, r'Invalid argument; .*'),
                        CommandReplyPilatus(
                            15, r'Set up rate correction: tau = (?P<tau>' + RE_FLOAT + r') s', defaults={'cutoff': None}),
                        reply_noaccess,
                        ], {'tau': float, 'cutoff': int}),
        Command('ExpTime', [CommandReplyPilatus(15, r'Illegal exposure time', defaults={'exptime': None}),
                            CommandReplyPilatus(
                                15, r'Exposure time set to: (?P<exptime>' + RE_FLOAT + r') sec.'),
                            reply_noaccess,
                            ], {'exptime': float}),
        Command('ExpPeriod', [CommandReplyPilatus(15, r'Exposure period set to: (?P<expperiod>' + RE_FLOAT + r') sec'),
                              CommandReplyPilatus(
                                  15, r'Illegal exposure period', defaults={'expperiod': None}),
                              reply_noaccess, ], {'expperiod': float}),
        Command('Exposure', [CommandReplyPilatus(15, r'Starting (?P<exptime>' + RE_FLOAT + r') second background: (?P<starttime>' + RE_DATE + r')', defaults={'filename': None}),
                             CommandReplyPilatus(
                                 7, r'(?P<filename>.*)', defaults={'starttime': None, 'exptime': None}),
                             reply_noaccess,
                             ], {'exptime': float, 'starttime': dateutil.parser.parse}),
        Command('Version', [CommandReplyPilatus(
            24, r'Code release:\s*(?P<version>.*)')], {'version': str}),
        Command('Telemetry', [CommandReplyPilatus(18, r'=== Telemetry at (?P<date>' + RE_DATE +
                                                  r') ===\s*\nImage format: (?P<Wpix>' + RE_INT + r')\(w\) x (?P<Hpix>' + RE_INT +
                                                  r')\(h\) pixels\s*\nSelected bank: (?P<sel_bank>' + RE_INT +
                                                  r')\s*\nSelected module: (?P<sel_module>' + RE_INT +
                                                  r')\s*\nSelected chip: (?P<sel_chip>' + RE_INT +
                                                  r')\s*\n(Channel ' + RE_INT + r': Temperature = ' +
                                                  RE_FLOAT + r'C, Rel. Humidity = ' +
                                                      RE_FLOAT + r'%\s*\n)*',
                                                  r'Channel (?P<channel>' + RE_INT +
                                                  r'): Temperature = (?P<temperature>' + RE_FLOAT +
                                                  r')C, Rel. Humidity = (?P<humidity>' + RE_FLOAT +
                                                  r')%')],
                {'date': dateutil.parser.parse, 'Wpix': int, 'Hpix': int, 'sel_bank': int, 'sel_module': int, 'sel_chip': int, 'channel': lambda lis: [int(x) for x in lis],
                 'temperature': lambda lis: [float(x) for x in lis], 'humidity': lambda lis: [float(x) for x in lis]}),
        Command('Df', [CommandReplyPilatus(
            5, r'(?P<diskfree>' + RE_INT + ')')], {'diskfree': int}),
        Command('SetThreshold', [CommandReplyPilatus(15, 'Settings: (?P<gain>\w+) gain; threshold: (?P<threshold>' + RE_INT + ') eV; vcmp: (?P<vcmp>' + RE_FLOAT + ') V\n\s*Trim file:\s*\n\s*(?P<trimfile>.*)'),
                                 CommandReplyPilatus(15, '/tmp/setthreshold\.cmd', defaults={
                                                     'gain': None, 'vcmp': np.nan, 'threshold': np.nan, 'trimfile': None}),
                                 CommandReplyPilatus(15, 'Threshold has not been set', defaults={
                                                     'gain': None, 'vcmp': np.nan, 'threshold': np.nan, 'trimfile': None}),
                                 CommandReplyPilatus(15, 'Requested threshold \(' + RE_FLOAT + ' eV\) is out of range', defaults={
                                                     'gain': None, 'vcmp': np.nan, 'threshold': np.nan, 'trimfile': None}),
                                 reply_noaccess,
                                 ], {'gain': str, 'threshold': float, 'vcmp': float, 'trimfile': str}),
        # use this to kill exposure when NImages >1
        Command('K', [CommandReplyPilatus(13, 'kill'), reply_noaccess]),
        # use this to kill exposure when NImages = 1
        Command('ResetCam', [CommandReplyPilatus(15, ''), reply_noaccess]),
        Command('NImages', [CommandReplyPilatus(15, 'N images set to: (?P<nimages>' + RE_INT + ')'),
                            reply_noaccess, ], {'nimages': int}),
        Command('THread', [CommandReplyPilatus(215, r'(Channel ' + RE_INT + r': Temperature = ' + RE_FLOAT + r'C, Rel. Humidity = ' + RE_FLOAT + r'%(;\n)?)*',
                                               r'Channel (?P<channel>' + RE_INT + r'): Temperature = (?P<temperature>' + RE_FLOAT + r')C, Rel. Humidity = (?P<humidity>' + RE_FLOAT + r')%')],
                {'channel': lambda lis: [int(x) for x in lis], 'temperature': lambda lis: [float(x) for x in lis], 'humidity': lambda lis: [float(x) for x in lis]}),
        Command('CamSetup', [CommandReplyPilatus(2, r"\n\s*Camera definition:\n\s+(?P<cameradef>.*)\n\s*Camera name: (?P<cameraname>.*),\sS/N\s(?P<cameraSN>" + RE_INT + \
                                                 r"-" + RE_INT + r")\n\s*Camera state: (?P<camstate>.*)\n\s*Target file: (?P<targetfile>.*)\n\s*Time left: (?P<timeleft>" + RE_FLOAT + \
                                                 r')\n\s*Last image: (?P<lastimage>.*)\n\s*Master PID is: (?P<masterPID>' + RE_INT + \
                                                 r')\n\s*Controlling PID is: (?P<controllingPID>' + RE_INT + \
                                                 r')\n\s*Exposure time: (?P<exptime>' + RE_FLOAT + \
                                                 r')\n\s*Last completed image:\s*\n\s*(?P<lastcompletedimage>.*)\n\s*Shutter is: (?P<shutterstate>.*)\n')],
                {'cameradef': str, 'cameraname': str, 'cameraSN': str, 'camstate': str, 'targetfile': str, 'timeleft': float, 'lastimage': str,
                 'masterPID': int, 'controllingPID': int, 'exptime': float, 'lastcompletedimage': str, 'shutterstate': str}),
        Command(
            'ImgPath', [CommandReplyPilatus(10, '(?P<imgpath>.*)'), reply_noaccess]),
        Command('ImgMode', [
                CommandReplyPilatus(15, 'ImgMode is (?P<imgmode>.*)'), reply_noaccess]),
        Command('ShowPID', [
                CommandReplyPilatus(16, 'PID = (?P<pid>' + RE_INT + ')')], {'pid': int}),
    ]
    gain = InstrumentProperty(
        name='gain', type=str, timeout=60, refreshinterval=60)
    threshold = InstrumentProperty(
        name='threshold', type=float, timeout=60, refreshinterval=60)
    trimfile = InstrumentProperty(
        name='trimfile', type=str, timeout=60, refreshinterval=60)
    vcmp = InstrumentProperty(
        name='vcmp', type=float, timeout=60, refreshinterval=60)
    wpix = InstrumentProperty(
        name='wpix', type=int, timeout=3600, refreshinterval=3600)
    hpix = InstrumentProperty(
        name='hpix', type=int, timeout=3600, refreshinterval=3600)
    temperature0 = InstrumentProperty(
        name='temperature0', type=list, timeout=30, refreshinterval=30)
    temperature1 = InstrumentProperty(
        name='temperature1', type=list, timeout=30, refreshinterval=30)
    temperature2 = InstrumentProperty(
        name='temperature2', type=list, timeout=30, refreshinterval=30)
    humidity0 = InstrumentProperty(
        name='humidity0', type=list, timeout=30, refreshinterval=30)
    humidity1 = InstrumentProperty(
        name='humidity1', type=list, timeout=30, refreshinterval=30)
    humidity2 = InstrumentProperty(
        name='humidity2', type=list, timeout=30, refreshinterval=30)
    cameraname = InstrumentProperty(
        name='cameraname', type=str, timeout=3600, refreshinterval=3600)
    camerasn = InstrumentProperty(
        name='camerasn', type=str, timeout=3600, refreshinterval=3600)
    timeleft = InstrumentProperty(
        name='timeleft', type=float, timeout=1, refreshinterval=1)
    exptime = InstrumentProperty(
        name='exptime', type=float, timeout=10, refreshinterval=10)
    expperiod = InstrumentProperty(
        name='expperiod', type=float, timeout=10, refreshinterval=10)
    nimages = InstrumentProperty(
        name='nimages', type=float, timeout=10, refreshinterval=10)
    tau = InstrumentProperty(
        name='tau', type=float, timeout=10, refreshinterval=10)
    cutoff = InstrumentProperty(
        name='cutoff', type=float, timeout=10, refreshinterval=10)
    imagesremaining = InstrumentProperty(
        name='imagesremaining', type=int, timeout=10, refreshinterval=10)
    default_threshold = GObject.property(
        type=int, default=4024, minimum=3814, maximum=20202, blurb='Default threshold value (eV)')
    default_gain = GObject.property(
        type=str, default='highG', blurb='Default gain')

    def __init__(self, name='detector', offline=True):
        self._OWG_init_lists()
        self._OWG_entrytypes[
            'default-gain'] = objwithgui.OWG_Param_Type.ListOfStrings
        self._OWG_hints[
            'default-gain'] = {objwithgui.OWG_Hint_Type.ChoicesList: ['lowG', 'midG', 'highG']}
        Instrument_TCP.__init__(self, name, offline)
        self._mesgseparator = '\x18'
        self.timeout = 1
        self._status_lock = threading.RLock()
        self._exposure_starttime = None
        self.logfile = 'log.pilatus300k'
        self._logging_parameters = [('threshold', 'f4', '%s'), ('gain', 'S5', '%s'), ('status', 'S20', '%s'),
                                    ('temperature0', 'f4', '%.2f'), ('temperature1',
                                                                     'f4', '%.2f'), ('temperature2', 'f4', '%.2f'),
                                    ('humidity0', 'f4', '%.1f'), ('humidity1', 'f4', '%.1f'), ('humidity2', 'f4', '%.1f'), ]

    def _logthread_worker(self):
        try:
            self._update_instrumentproperties(None)
            with self._status_lock:
                Instrument_TCP._logthread_worker(self)
        except InstrumentPropertyUnknown as ipu:
            logger.warning(
                'Skipping log line because of unknown instrument property: ' + traceback.format_exc())

    def _update_instrumentproperties(self, propertyname=None):
        with self._status_lock:
            if propertyname is not None:
                toupdate = [propertyname]
            else:
                toupdate = [x for x in self._get_instrumentproperties(
                ) if self.is_instrumentproperty_expired(x)]
            if self.status == PilatusStatus.ExposingMulti:
                if 'timeleft' in toupdate:
                    type(self).timeleft._update(self, (self._instrumentproperties['nimages'][
                        0] * self._instrumentproperties['expperiod'][0] - (time.time() - self._exposure_starttime)), InstrumentPropertyCategory.NORMAL)
                if 'imagesremaining' in toupdate:
                    type(self).imagesremaining._update(self, self._instrumentproperties['nimages'][
                        0] - math.floor((time.time() - self._exposure_starttime) / self._instrumentproperties['expperiod'][0]), InstrumentPropertyCategory.NORMAL)
                for key in [k for k in toupdate if k not in ('timeleft', 'imagesremaining')]:
                    getattr(type(self), key)._update(
                        self, self._instrumentproperties[key][0], self._instrumentproperties[key][2])
                return  # cannot update anything.
            if self.status == PilatusStatus.Trimming:
                for key in toupdate:
                    getattr(type(self), key)._update(
                        self, self._instrumentproperties[key][0], self._instrumentproperties[key][2])
                return  # cannot update anything.
            if self.status not in [PilatusStatus.Exposing, PilatusStatus.ExposingMulti]:
                type(self).timeleft._update(
                    self, 0, InstrumentPropertyCategory.NORMAL)
                type(self).imagesremaining._update(
                    self, 0, InstrumentPropertyCategory.NORMAL)
                if 'timeleft' in toupdate:
                    toupdate.remove('timeleft')
                if 'imagesremaining' in toupdate:
                    toupdate.remove('imagesremaining')
            if {'gain', 'threshold', 'vcmp', 'trimfile'}.intersection(toupdate):
                try:
                    thresholdsettings = self._get_general('SetThreshold')
                except InstrumentError as ie:
                    logger.warn(
                        'InstrumentError on updating threshold-like parameters: ' + traceback.format_exc())
                    for key in ['gain', 'threshold', 'vcmp', 'trimfile']:
                        getattr(type(self), key)._update(
                            self, None, InstrumentPropertyCategory.UNKNOWN)
                else:
                    type(self).gain._update(
                        self, thresholdsettings['gain'], InstrumentPropertyCategory.NORMAL)
                    type(self).threshold._update(
                        self, thresholdsettings['threshold'], InstrumentPropertyCategory.NORMAL)
                    type(self).vcmp._update(
                        self, thresholdsettings['vcmp'], InstrumentPropertyCategory.NORMAL)
                    type(self).trimfile._update(
                        self, thresholdsettings['trimfile'], InstrumentPropertyCategory.NORMAL)
            if {'wpix', 'hpix'}.intersection(toupdate):
                try:
                    telemetry = self.get_telemetry()
                except InstrumentError as ie:
                    logger.warn(
                        'InstrumentError on updating telemetry parameters: ' + traceback.format_exc())
                    for key in ['wpix', 'hpix'] + ['temperature%d' % i for i in range(3)] + ['humidity%d' % i for i in range(3)]:
                        getattr(type(self), key)._update(
                            self, None, InstrumentPropertyCategory.UNKNOWN)
                else:
                    type(self).wpix._update(
                        self, telemetry['Wpix'], InstrumentPropertyCategory.NORMAL)
                    type(self).hpix._update(
                        self, telemetry['Hpix'], InstrumentPropertyCategory.NORMAL)
                    for i in range(3):
                        if (telemetry['temperature'][i] <= TEMPERATURE_ERROR_LIMITS[i][0]) or (telemetry['temperature'][i] >= TEMPERATURE_ERROR_LIMITS[i][1]):
                            getattr(type(self), 'temperature%d' % i)._update(
                                self, telemetry['temperature'][i], InstrumentPropertyCategory.ERROR)
                        elif (telemetry['temperature'][i] <= TEMPERATURE_WARNING_LIMITS[i][0]) or (telemetry['temperature'][i] >= TEMPERATURE_WARNING_LIMITS[i][1]):
                            getattr(type(self), 'temperature%d' % i)._update(
                                self, telemetry['temperature'][i], InstrumentPropertyCategory.WARNING)
                        else:
                            getattr(type(self), 'temperature%d' % i)._update(
                                self, telemetry['temperature'][i], InstrumentPropertyCategory.OK)
                        if (telemetry['humidity'][i] >= HUMIDITY_ERROR_LIMITS[i]):
                            getattr(type(self), 'humidity%d' % i)._update(
                                self, telemetry['humidity'][i], InstrumentPropertyCategory.ERROR)
                        elif (telemetry['humidity'][i] >= HUMIDITY_WARNING_LIMITS[i]):
                            getattr(type(self), 'humidity%d' % i)._update(
                                self, telemetry['humidity'][i], InstrumentPropertyCategory.WARNING)
                        else:
                            getattr(type(self), 'humidity%d' % i)._update(
                                self, telemetry['humidity'][i], InstrumentPropertyCategory.OK)
                    for key in [key for key in toupdate if key.startswith('humidity') or key.startswith('temperature')]:
                        toupdate.remove(key)
            if [key for key in toupdate if key.startswith('humidity') or key.startswith('temperature')]:
                try:
                    temphum = self.get_temperature_humidity()
                except InstrumentError as ie:
                    logger.warn(
                        'InstrumentError on updating temperature-humidity parameters: ' + traceback.format_exc())
                    for key in ['temperature%d' % i for i in range(3)] + ['humidity%d' % i for i in range(3)]:
                        getattr(type(self), key)._update(
                            self, None, InstrumentPropertyCategory.UNKNOWN)
                else:
                    for i in range(3):
                        if (temphum['temperature'][i] <= TEMPERATURE_ERROR_LIMITS[i][0]) or (temphum['temperature'][i] >= TEMPERATURE_ERROR_LIMITS[i][1]):
                            getattr(type(self), 'temperature%d' % i)._update(
                                self, temphum['temperature'][i], InstrumentPropertyCategory.ERROR)
                        elif (temphum['temperature'][i] <= TEMPERATURE_WARNING_LIMITS[i][0]) or (temphum['temperature'][i] >= TEMPERATURE_WARNING_LIMITS[i][1]):
                            getattr(type(self), 'temperature%d' % i)._update(
                                self, temphum['temperature'][i], InstrumentPropertyCategory.WARNING)
                        else:
                            getattr(type(self), 'temperature%d' % i)._update(
                                self, temphum['temperature'][i], InstrumentPropertyCategory.OK)
                        if (temphum['humidity'][i] >= HUMIDITY_ERROR_LIMITS[i]):
                            getattr(type(self), 'humidity%d' % i)._update(
                                self, temphum['humidity'][i], InstrumentPropertyCategory.ERROR)
                        elif (temphum['humidity'][i] >= HUMIDITY_WARNING_LIMITS[i]):
                            getattr(type(self), 'humidity%d' % i)._update(
                                self, temphum['humidity'][i], InstrumentPropertyCategory.WARNING)
                        else:
                            getattr(type(self), 'humidity%d' % i)._update(
                                self, temphum['humidity'][i], InstrumentPropertyCategory.OK)
                    for key in [key for key in toupdate if key.startswith('humidity') or key.startswith('temperature')]:
                        toupdate.remove(key)
            if 'nimages' in toupdate:
                try:
                    type(self).nimages._update(
                        self, self.get_nimages(), InstrumentPropertyCategory.NORMAL)
                except InstrumentError as ie:
                    logger.warn(
                        'InstrumentError on updating nimages: ' + traceback.format_exc())
                    type(self).nimages._update(
                        self, None, InstrumentPropertyCategory.UNKNOWN)
            if {'cameraname', 'camerasn', 'timeleft', 'exptime'}.intersection(toupdate):
                try:
                    camsetup = self.camsetup()
                except InstrumentError as ie:
                    logger.warn(
                        'InstrumentError on updating camsetup parameters: ' + traceback.format_exc())
                    for key in ['cameraname', 'camerasn', 'timeleft', 'exptime']:
                        getattr(type(self), key)._update(
                            self, None, InstrumentPropertyCategory.UNKNOWN)
                else:
                    type(self).cameraname._update(
                        self, camsetup['cameraname'], InstrumentPropertyCategory.NORMAL)
                    type(self).camerasn._update(
                        self, camsetup['cameraSN'], InstrumentPropertyCategory.NORMAL)
                    type(self).timeleft._update(
                        self, camsetup['timeleft'], InstrumentPropertyCategory.NORMAL)
                    type(self).exptime._update(
                        self, camsetup['exptime'], InstrumentPropertyCategory.NORMAL)
            if 'expperiod' in toupdate:
                try:
                    type(self).expperiod._update(
                        self, self.get_expperiod(), InstrumentPropertyCategory.NORMAL)
                except InstrumentError as ie:
                    logger.warn(
                        'InstrumentError on updating expperiod: ' + traceback.format_exc())
                    type(self).expperiod._update(
                        self, None, InstrumentPropertyCategory.UNKNOWN)
            if {'tau', 'cutoff'}.intersection(toupdate):
                try:
                    taudata = self._get_general('Tau', None)
                except InstrumentError as ie:
                    logger.warn(
                        'InstrumentError on updating tau-like parameters: ' + traceback.format_exc())
                    for key in ['tau', 'cutoff']:
                        getattr(type(self), key)._update(
                            self, None, InstrumentPropertyCategory.UNKNOWN)
                else:
                    type(self).tau._update(
                        self, taudata['tau'], InstrumentPropertyCategory.NORMAL)
                    type(self).cutoff._update(
                        self, taudata['cutoff'], InstrumentPropertyCategory.NORMAL)
            if 'imagesremaining' in toupdate:
                if self.status == PilatusStatus.Exposing:
                    type(self).imagesremaining._update(
                        self, 1, InstrumentPropertyCategory.NORMAL)
                elif self.status != PilatusStatus.Disconnected:
                    type(self).imagesremaining._update(
                        self, 0, InstrumentPropertyCategory.NORMAL)
                else:
                    type(self).imagesremaining._update(
                        self, None, InstrumentPropertyCategory.UNKNOWN)

    def _process_results(self, dic):
        with self._status_lock:
            if (dic['command'] == 'SetThreshold') and (self.status == PilatusStatus.Trimming):
                with self.freeze_notify():
                    self.status = PilatusStatus.Idle
                    self._update_instrumentproperties('threshold')
            elif dic['command'] == 'Exposure' and dic['filename'] is not None:
                with self.freeze_notify():
                    self.status = PilatusStatus.Idle
                    self._update_instrumentproperties()

        if dic['status'] == 'ERR':
            logger.error('Command %s returned error!' % dic['command'])

    def interpret_message(self, message, command=None, putback_if_no_match=True):
        if command is not None:
            cmdlist = [
                c for c in self._commands if c.command.lower() == command.lower()]
        else:
            cmdlist = self._commands
        for c in cmdlist:
            m = c.match(message)
            if m is not None:
                m['command'] = c.command
                self._process_results(m)
                return m
        # we reach here if the message could not be matched.
        if command is None:
            # this means we tried all the commands and nothing matched the
            # message
            logger.warning('Cannot match message: ' + message)
            return None
        else:
            # maybe this is not the message for us: queue it back
            if putback_if_no_match:
                self._inqueue.put(message)
            else:
                raise PilatusError(
                    'Cannot match message, putback disabled: ' + message)
            return None

    def _post_connect(self):
        with self._status_lock:
            self._invalidate_instrumentproperties()
        if self.camsetup()['controllingPID'] != self.get_pid():
            raise PilatusError('Cannot establish read-write connection!')
        self._update_instrumentproperties()
        self.set_threshold(self.default_threshold, self.default_gain)

    def camsetup(self):
        message = self.send_and_receive('CamSetup', blocking=True)
        mesg = self.interpret_message(message, 'CamSetup')
        if mesg is None:
            raise PilatusError('Invalid message: ' + message)
        return mesg

    def send_and_receive(self, command, blocking=True):
        return Instrument_TCP.send_and_receive(self, command + '\n', blocking)

    def is_fullaccess(self):
        return self.camsetup()['controllingPID'] == self.get_pid()

    def get_pid(self):
        return self._get_general('ShowPID', 'pid')

    def set_nimages(self, nimages):
        mesg = self._set_general('NImages', 'nimages', '%d', nimages)
        self._update_instrumentproperties('nimages')
        return mesg

    def get_nimages(self):
        return self._get_general('NImages', 'nimages')

    def set_exptime(self, exptime):
        mesg = self._set_general('ExpTime', 'exptime', '%f', exptime)
        self._update_instrumentproperties('exptime')
        return mesg

    def get_exptime(self):
        return self._get_general('ExpTime', 'exptime')

    def set_expperiod(self, expperiod):
        mesg = self._set_general('ExpPeriod', 'expperiod', '%f', expperiod)
        self._update_instrumentproperties('expperiod')
        return mesg

    def get_expperiod(self):
        return self._get_general('ExpPeriod', 'expperiod')

    def set_imgpath(self, imgpath):
        return self._set_general('ImgPath', 'imgpath', '%s', imgpath)

    def get_imgpath(self):
        return self._get_general('ImgPath', 'imgpath')

    def set_tau(self, tau):
        mesg = self._set_general('Tau', 'tau', '%f', tau)
        self._update_instrumentproperties('tau')
        return mesg

    def get_tau(self):
        return self._get_general('Tau', 'tau')

    def get_cutoff(self):
        return self._get_general('Tau', 'cutoff')

    def get_df(self):
        return self._get_general('Df', 'diskfree')

    def set_imgmode(self, imgmode):
        return self._set_general('ImgMode', 'imgmode', '%s', imgmode)

    def get_imgmode(self):
        return self._get_general('ImgMode', 'imgmode')

    def get_threshold(self):
        return self._get_general('SetThreshold', 'threshold')

    def get_gain(self):
        return self._get_general('SetThreshold', 'gain')

    def get_vcmp(self):
        return self._get_general('SetThreshold', 'vcmp')

    def get_trimfile(self):
        return self._get_general('SetThreshold', 'trimfile')

    def set_threshold(self, threshold, gain=None):
        if gain is None:
            self.send_and_receive(
                'SetThreshold %d' % threshold, blocking=False)
        else:
            if not gain.upper().endswith('G'):
                gain = gain + 'G'
            self.send_and_receive('SetThreshold %s %d' %
                                  (gain, threshold), blocking=False)
        with self._status_lock:
            self.status = PilatusStatus.Trimming

    def get_temperature_humidity(self):
        return self._get_general('THread', None)

    def get_telemetry(self):
        return self._get_general('Telemetry', None)

    def _set_general(self, command, key, formatstr, value):
        message = self.send_and_receive(
            command + ' ' + formatstr % value, blocking=True)
        mesg = self.interpret_message(message, command)
        if mesg is None:
            raise PilatusError(
                'Invalid message for ' + command + ': ' + message)
        if key is None:
            return mesg
        else:
            return mesg[key]

    def _get_general(self, command, key=None):
        message = self.send_and_receive(command, blocking=True)
        mesg = self.interpret_message(message, command)
        if mesg is None:
            raise PilatusError(
                'Invalid message for ' + command + ': ' + message)
        if key is None:
            return mesg
        else:
            return mesg[key]

    def _get_command(self, command):
        return Instrument_TCP._get_command(self, command.split()[0].strip())

    def prepare_exposure(self, exptime, nimages=1, dwelltime=0.003):
        exptime = self.set_exptime(exptime)
        nimages = self.set_nimages(nimages)
        if dwelltime is None:
            dwelltime = 0.003
        self.set_expperiod(dwelltime + exptime)

    def execute_exposure(self, filename):
        nimages = self.get_nimages()
        try:
            with self._status_lock:
                if nimages == 1:
                    self.status = PilatusStatus.Exposing
                else:
                    self.status = PilatusStatus.ExposingMulti
            self._exposure_starttime = time.time()
            message = self.send_and_receive(
                'Exposure ' + filename, blocking=True)
            mesg = self.interpret_message(message, 'Exposure')
            self._update_instrumentproperties('timeleft')
            self._update_instrumentproperties('imagesremaining')
            if mesg is None:
                raise PilatusError('Invalid message for Exposure: ' + message)
        except:
            with self._status_lock:
                self.status = PilatusStatus.Idle
            raise
        days, secs = divmod(mesg['exptime'], (24 * 60 * 60))
        secs, usecs = divmod(secs, 1)
        return mesg['starttime'], mesg['exptime'], mesg['starttime'] + datetime.timedelta(days, secs, 1e6 * usecs)

    def expose(self, exptime, filename, nimages=1, dwelltime=0.003):
        self.prepare_exposure(exptime, nimages, dwelltime)
        return self.execute_exposure(filename)

    def stopexposure(self):
        with self._status_lock:
            if self.status == PilatusStatus.Exposing:
                return self.resetcam()
            elif self.status == PilatusStatus.ExposingMulti:
                message = self.send_and_receive('K', blocking=True)
                mesg = self.interpret_message(message, 'K')
                if mesg is None:
                    raise PilatusError('Invalid message for K: ' + message)
                return mesg['status'] == 'ERR'
            else:
                raise PilatusError('No exposure running!')

    def resetcam(self):
        message = self.send_and_receive('ResetCam', blocking=True)
        mesg = self.interpret_message(message, 'ResetCam')
        if mesg is None:
            raise PilatusError('Invalid message for ResetCam: ' + message)
        return mesg['status'] == 'OK'

    def get_current_parameters(self):
        return {ip: self._instrumentproperties[ip][0] for ip in self._instrumentproperties}

    def get_timeleft(self):
        return self.camsetup()['timeleft']
