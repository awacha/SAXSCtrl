from .instrument import Instrument_TCP, InstrumentError, InstrumentStatus, Command, CommandReply
import dateutil.parser
import re
import socket
import logging
import datetime

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

RE_FLOAT = r"[+-]?(\d+)*\.?\d+([eE][+-]?\d+)?"
RE_DATE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+"
RE_INT = r"[+-]?\d+"



class CommandReplyPilatus(CommandReply):
    def __init__(self, context, regex, findall_regex=None, defaults=None):
        CommandReply.__init__(self, r'(?P<context>\d+)\s+(?P<status>[A-Z]+)\s+' + regex, findall_regex, defaults)
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
    _commands = [
        Command('Tau', [CommandReplyPilatus(15, r'Rate correction is on; tau = (?P<tau>' + RE_FLOAT + r') s, cutoff = (?P<cutoff>' + RE_INT + r') counts'),
                        CommandReplyPilatus(15, r'Turn off rate correction', defaults={'tau':0, 'cutoff':1048574}),
                        CommandReplyPilatus(15, r'Rate correction is off, cutoff = (?P<cutoff>' + RE_INT + r') counts', defaults={'tau':0}),
                        CommandReplyPilatus(15, r'Invalid argument; .*'),
                        CommandReplyPilatus(15, r'Set up rate correction: tau = (?P<tau>' + RE_FLOAT + r') s', defaults={'cutoff':None}),
                        reply_noaccess,
                        ], {'tau':float, 'cutoff':int}),
        Command('ExpTime', [CommandReplyPilatus(15, r'Illegal exposure time', defaults={'exptime':None}),
                            CommandReplyPilatus(15, r'Exposure time set to: (?P<exptime>' + RE_FLOAT + r') sec.'),
                            reply_noaccess,
                            ], {'exptime':float}),
        Command('ExpPeriod', [CommandReplyPilatus(15, r'Exposure period set to: (?P<expperiod>' + RE_FLOAT + r') sec'),
                              CommandReplyPilatus(15, r'Illegal exposure period', defaults={'expperiod':None}),
                              reply_noaccess, ], {'expperiod':float}),
        Command('Exposure', [CommandReplyPilatus(15, r'Starting (?P<exptime>' + RE_FLOAT + r') second background: (?P<starttime>' + RE_DATE + r')', defaults={'filename':None}),
                             CommandReplyPilatus(7, r'(?P<filename>.*)', defaults={'starttime':None, 'exptime':None}),
                             reply_noaccess,
                             ], {'exptime':float, 'starttime':dateutil.parser.parse}),
        Command('Version', [CommandReplyPilatus(24, r'Code release:\s*(?P<version>.*)')], {'version':str}),
        Command('Telemetry', [CommandReplyPilatus(18, r'=== Telemetry at (?P<date>' + RE_DATE + \
                                          r') ===\s*\nImage format: (?P<Wpix>' + RE_INT + r')\(w\) x (?P<Hpix>' + RE_INT + \
                                          r')\(h\) pixels\s*\nSelected bank: (?P<sel_bank>' + RE_INT + \
                                          r')\s*\nSelected module: (?P<sel_module>' + RE_INT + \
                                          r')\s*\nSelected chip: (?P<sel_chip>' + RE_INT + \
                                          r')\s*\n(Channel ' + RE_INT + r': Temperature = ' + RE_FLOAT + r'C, Rel. Humidity = ' + RE_FLOAT + r'%\s*\n)*',
                                          r'Channel (?P<channel>' + RE_INT + \
                                          r'): Temperature = (?P<temperature>' + RE_FLOAT + \
                                          r')C, Rel. Humidity = (?P<humidity>' + RE_FLOAT + \
                                          r')%') ],
                             {'date':dateutil.parser.parse, 'Wpix':int, 'Hpix':int, 'sel_bank':int, 'sel_module':int, 'sel_chip':int, 'channel':lambda lis: [int(x) for x in lis],
                              'temperature': lambda lis: [float(x) for x in lis], 'humidity': lambda lis: [float(x) for x in lis]}),
        Command('Df', [CommandReplyPilatus(5, r'(?P<diskfree>' + RE_INT + ')')], {'diskfree':int}),
        Command('SetThreshold', [CommandReplyPilatus(15, 'Settings: (?P<gain>\w+) gain; threshold: (?P<threshold>' + RE_INT + ') eV; vcmp: (?P<vcmp>' + RE_FLOAT + ') V\n\s*Trim file:\s*\n\s*(?P<trimfile>.*)'),
                               CommandReplyPilatus(15, '/tmp/setthreshold\.cmd', defaults={'gain':None, 'vcmp':None, 'threshold':None, 'trimfile':None}),
                               CommandReplyPilatus(15, 'Threshold has not been set', defaults={'gain':None, 'vcmp':None, 'threshold':None, 'trimfile':None}),
                               CommandReplyPilatus(15, 'Requested threshold \(' + RE_FLOAT + ' eV\) is out of range', defaults={'gain':None, 'vcmp':None, 'threshold':None, 'trimfile':None}),
                               reply_noaccess,
                               ], {'gain':str, 'threshold':float, 'vcmp':float, 'trimfile':str}),
        Command('K', [CommandReplyPilatus(13, 'kill'), reply_noaccess]),  # use this to kill exposure when NImages >1
        Command('ResetCam', [CommandReplyPilatus(15, ''), reply_noaccess]),  # use this to kill exposure when NImages = 1
        Command('NImages', [CommandReplyPilatus(15, 'N images set to: (?P<nimages>' + RE_INT + ')'),
                             reply_noaccess, ], {'nimages':int}),
        Command('THread', [CommandReplyPilatus(215, r'(Channel ' + RE_INT + r': Temperature = ' + RE_FLOAT + r'C, Rel. Humidity = ' + RE_FLOAT + r'%(;\n)?)*',
                                        r'Channel (?P<channel>' + RE_INT + r'): Temperature = (?P<temperature>' + RE_FLOAT + r')C, Rel. Humidity = (?P<humidity>' + RE_FLOAT + r')%')],
                {'channel':lambda lis: [int(x) for x in lis], 'temperature': lambda lis: [float(x) for x in lis], 'humidity': lambda lis: [float(x) for x in lis]}),
        Command('CamSetup', [CommandReplyPilatus(2, r"\n\s*Camera definition:\n\s+(?P<cameradef>.*)\n\s*Camera name: (?P<cameraname>.*),\sS/N\s(?P<cameraSN>" + RE_INT + \
                                          r"-" + RE_INT + r")\n\s*Camera state: (?P<camstate>.*)\n\s*Target file: (?P<targetfile>.*)\n\s*Time left: (?P<timeleft>" + RE_FLOAT + \
                                          r')\n\s*Last image: (?P<lastimage>.*)\n\s*Master PID is: (?P<masterPID>' + RE_INT + \
                                          r')\n\s*Controlling PID is: (?P<controllingPID>' + RE_INT + \
                                          r')\n\s*Exposure time: (?P<exptime>' + RE_FLOAT + \
                                          r')\n\s*Last completed image:\s*\n\s*(?P<lastcompletedimage>.*)\n\s*Shutter is: (?P<shutterstate>.*)\n')],
                {'cameradef':str, 'cameraname':str, 'cameraSN':str, 'camstate':str, 'targetfile':str, 'timeleft':float, 'lastimage':str,
                 'masterPID':int, 'controllingPID':int, 'exptime':float, 'lastcompletedimage':str, 'shutterstate':str}),
        Command('ImgPath', [CommandReplyPilatus(10, '(?P<imgpath>.*)'), reply_noaccess]),
        Command('ImgMode', [CommandReplyPilatus(15, 'ImgMode is (?P<imgmode>.*)'), reply_noaccess]),
        Command('ShowPID', [CommandReplyPilatus(16, 'PID = (?P<pid>' + RE_INT + ')')], {'pid':int}),
                  ]
    def __init__(self):
        Instrument_TCP.__init__(self)
        self._mesgseparator = '\x18'
        self.timeout = 1
    def _process_results(self, dic):
        if (dic['command'] == 'SetThreshold') and (self.status != PilatusStatus.Idle):
            self.status = PilatusStatus.Idle
        elif dic['command'] == 'Exposure' and dic['filename'] is not None:
            self.status = PilatusStatus.Idle
        if dic['status'] == 'ERR':
            logger.error('Command %s returned error!' % dic['command'])
    def interpret_message(self, message, command=None, putback_if_no_match=True):
        if command is not None:
            cmdlist = [ c for c in self._commands if c.command.lower() == command.lower()]
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
            # this means we tried all the commands and nothing matched the message
            logger.warning('Cannot match message: ' + message)
            return None
        else:
            # maybe this is not the message for us: queue it back
            if putback_if_no_match:
                self._inqueue.put(message)
            else:
                raise PilatusError('Cannot match message, putback disabled: ' + message)
            return None
        
    def _post_connect(self):
        if self.camsetup()['controllingPID'] != self.get_pid():
            raise PilatusError('Cannot establish read-write connection!')
        self.set_threshold(4024)
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
        return self._set_general('NImages', 'nimages', '%d', nimages)
    def get_nimages(self):
        return self._get_general('NImages', 'nimages')
    def set_exptime(self, exptime):
        return self._set_general('ExpTime', 'exptime', '%f', exptime)
    def get_exptime(self):
        return self._get_general('ExpTime', 'exptime')
    def set_expperiod(self, expperiod):
        return self._set_general('ExpPeriod', 'expperiod', '%f', expperiod)
    def get_expperiod(self):
        return self._get_general('ExpPeriod', 'expperiod')
    def set_imgpath(self, imgpath):
        return self._set_general('ImgPath', 'imgpath', '%s', imgpath)
    def get_imgpath(self):
        return self._get_general('ImgPath', 'imgpath')
    def set_tau(self, tau):
        return self._set_general('Tau', 'tau', '%f', tau)
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
            message = self.send_and_receive('SetThreshold %d' % threshold, blocking=False)
        else:
            message = self.send_and_receive('SetThreshold %s %d' % (gain, threshold), blocking=False)
        self.status = PilatusStatus.Trimming
    def get_temperature_humidity(self):
        return self._get_general('THread', None)
    def get_telemetry(self):
        return self._get_general('Telemetry', None)
    def _set_general(self, command, key, formatstr, value):
        message = self.send_and_receive(command + ' ' + formatstr % value, blocking=True)
        mesg = self.interpret_message(message, command)
        if mesg is None:
            raise PilatusError('Invalid message for ' + command + ': ' + message)
        if key is None:
            return mesg
        else:
            return mesg[key]
    def _get_general(self, command, key):
        message = self.send_and_receive(command, blocking=True)
        mesg = self.interpret_message(message, command)
        if mesg is None:
            raise PilatusError('Invalid message for ' + command + ': ' + message)
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
            if nimages == 1:
                self.status = PilatusStatus.Exposing
            else:
                self.status = PilatusStatus.ExposingMulti
            message = self.send_and_receive('Exposure ' + filename, blocking=True)
            mesg = self.interpret_message(message, 'Exposure')
            if mesg is None:
                raise PilatusError('Invalid message for Exposure: ' + message)
        except:
            self.status = PilatusStatus.Idle
            raise
        days, secs = divmod(mesg['exptime'], (24 * 60 * 60))
        secs, usecs = divmod(secs, 1)
        return mesg['starttime'], mesg['exptime'], mesg['starttime'] + datetime.timedelta(days, secs, 1e6 * usecs)
    def expose(self, exptime, filename, nimages=1, dwelltime=0.003):
        self.prepare_exposure(exptime, nimages, dwelltime)
        return self.execute_exposure(filename)
    
    def stopexposure(self):
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
        if not self.is_idle():
            dic = {}
        else:
            dic = self.get_telemetry()
            dic.update(self.camsetup())
            dic['imgmode'] = self.get_imgmode()
            dic['imgpath'] = self.get_imgpath()
            dic['PID'] = self.get_pid()
            dic['diskfree'] = self.get_df()
            del dic['status']
            del dic['context']
        return dic
    def get_timeleft(self):
        return self.camsetup()['timeleft']

                
        
        
        
            
