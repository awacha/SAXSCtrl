from gi.repository import Gtk
from gi.repository import GObject
from .widgets import ToolDialog
from ..hardware.instruments import genix
from gi.repository import GtkSource
from gi.repository import Pango
from gi.repository import Gdk
from gi.repository import GLib
import time
import re
import os

import logging


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RE_FLOAT = r"[+-]?(\d+)*\.?\d+([eE][+-]?\d+)?"
RE_DATE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+"
RE_INT = r"[+-]?\d+"
RE_FLOAT_OR_EXPRESSION = r"(" + RE_FLOAT + "|\{.*\}|§)"
RE_BOOL = '(0|1|True|False|Yes|No|y|n)'

def _parse_bool(mesg):
    if mesg.upper().strip() in ['1', 'TRUE', 'YES', 'Y']:
        return True
    elif mesg.upper().strip() in ['0', 'FALSE', 'NO', 'N', '']:
        return False
    else:
        return ValueError('Cannot decide if %s is to be considered true or false.' % mesg)

class ErrorSeverity(object):
    normal = 0
    critical = 1
    fatal = 2

class SequenceSyntaxError(StandardError):
    pass

class SequenceError(StandardError):
    """To be raised by sequence commands if some error happens.

    Severity should be:
        normal (0) if the error is not so severe, i.e. the sequence can
            be continued.
        fatal (1) if the sequence should be broken
        critical (2) if the error condition can make the instrument unstable.
    """
    def __init__(self, message, severity=ErrorSeverity.normal):
        StandardError.__init__(self, message)
        self.severity = severity

class JumpException(Exception):
    """To be raised by sequence commands if a jump to a label is requested.
    The message should be the label name."""
    def __init__(self, *args, **kwargs):
        if 'setstack' in kwargs:
            self.setstack = bool(kwargs['setstack'])
            del kwargs['setstack']
        else:
            self.setstack = False
        Exception.__init__(self, *args, **kwargs)

class KillException(Exception):
    pass

class SeqCommand(GObject.GObject):
    __gsignals__ = {'progress':(GObject.SignalFlags.RUN_FIRST, None, (str, float)),
                    'pulse':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'return':(GObject.SignalFlags.RUN_FIRST, None, (object, str, object)),  # object, return status, aux return parameters (jump to label etc.)
                    }
    command = None
    cmd_regex = ''
    signal_intervals = {'progress':1, 'pulse':0.5}
    _signal_lastemit = None
    _arguments = []
    def __init__(self):
        GObject.GObject.__init__(self)
        self._kill = False
        self._signal_lastemit = {}
    def match(self, cmdline):
        m = re.match('^' + self.cmd_regex + '$', cmdline, re.IGNORECASE)
        if m is None:
            return False
        for prop in m.groupdict():
            self.__setattr__(prop, m.groupdict()[prop])
        return True

    def execute(self, credo, prevval, variables):
        """Execute the command. Return only if the execution finished either normally or by a break.

        Should return True or raise an exception.

        """
        pass

    def simulate(self, credo, prevval, variables):
        pass

    def execute_command(self, credo, prevval, variables, simulate=False):
        """ Wrapper for the execute() method.

        Should emit the 'return' signal with the return value as an argument to it. If an error occurs
        (exception raised), 'fail' signal is emitted with the exception object. In this case, 'return'
        should not be emitted.
        """
        try:
            if simulate:
                result = self.simulate(credo, prevval, variables)
            else:
                result = self.execute(credo, prevval, variables)
            self.emit('return', result, 'OK', None)
        except KillException as ke:
            self.emit('return', None, 'KILL', ke.args)
        except JumpException as je:
            self.emit('return', je.args[0], 'JUMP', je.setstack)
        except Exception as ex:
            self.emit('return', ex, 'FAIL', None)
        return False  # we return False, because we will be an idle routine. Returning false ensures that we won't get rescheduled.
    def _parse_expressions(self, credo, prevval, variables):
        for a in self._arguments:
            value = self.__getattribute__(a)
            if isinstance(value, basestring) and value.startswith('{') and value.endswith('}'):
                self.__setattr__(a, eval(value[1:-1].replace('§', '(' + str(prevval) + ')'), globals(), variables))
            elif isinstance(value, basestring) and value == '§':
                self.__setattr__(a, prevval)

    def break_execution(self):
        self._kill = True
        pass
    def limited_emit(self, signalname, *args):
        if signalname in self.signal_intervals:
            if signalname not in self._signal_lastemit:
                self._signal_lastemit[signalname] = 0
            t = time.time()
            if t - self._signal_lastemit[signalname] > self.signal_intervals[signalname]:
                self._signal_lastemit[signalname] = t
                return self.emit(signalname, *args)
        else:
            return self.emit(signalname, *args)

class SeqCommandComment(SeqCommand):
    command = '<comment>'
    cmd_regex = '#.*'
    def execute(self, credo, prevval, variables):
        return prevval

class SeqCommandEmpty(SeqCommand):
    command = '<empty>'
    cmd_regex = ''
    def execute(self, credo, prevval, variables):
        return prevval

class SeqCommandGenixPower(SeqCommand):
    command = 'xray_power'
    cmd_regex = 'xray_power\s+(?P<level>(low|full|off))'
    level = 'off'
    _arguments = ['level']
    def execute(self, credo, prevval, variables):
        self._kill = False
        try:
            g = credo.get_equipment('genix')
        except Exception as exc:
            raise SequenceError(str(exc), ErrorSeverity.critical)
        if not g.connected():
            raise SequenceError('X-ray source not connected', ErrorSeverity.fatal)
        logger.info('Setting GeniX power to ' + self.level)
        if self.level.lower() == 'low':
            g.do_standby()
            waitstate = genix.GenixStatus.Standby
        elif self.level.lower() == 'full':
            g.do_rampup()
            waitstate = genix.GenixStatus.FullPower
        elif self.level.lower() == 'off':
            g.do_poweroff()
            waitstate = genix.GenixStatus.PowerDown
        else:
            raise SequenceError('Invalid power level: ' + self.level, ErrorSeverity.fatal)
        g.wait_for_status(waitstate, self._handler)
        if self._kill:
            raise KillException()
    def _handler(self):
        self.limited_emit('pulse', 'Setting GeniX power to ' + self.level)
        return self._kill
    def simulate(self, credo, prevval, variables):
        logger.info('Simulating: setting Genix Power to ' + self.level)

class SeqCommandGenixXrayState(SeqCommand):
    command = 'xray'
    cmd_regex = 'xray\s+(?P<level>(on|off))'
    level = 'off'
    _arguments = ['level']
    def execute(self, credo, prevval, variables):
        self._kill = False
        try:
            g = credo.get_equipment('genix')
        except Exception as exc:
            raise SequenceError(str(exc), ErrorSeverity.critical)
        if not g.connected():
            raise SequenceError('X-ray source not connected', ErrorSeverity.fatal)
        if self.level.lower() == 'on':
            g.xrays_on()
        elif self.level.lower() == 'off':
            g.xrays_off()
        else:
            raise SequenceError('Invalid X-ray state: ' + self.level, ErrorSeverity.fatal)
        logger.info('X-rays are ' + self.level.lower() + '.')

class SeqCommandGenixShutterState(SeqCommand):
    command = 'shutter'
    cmd_regex = 'shutter\s+(?P<level>(open|close))'
    level = 'close'
    _arguments = ['level']
    def execute(self, credo, prevval, variables):
        self._kill = False
        try:
            g = credo.get_equipment('genix')
        except Exception as exc:
            raise SequenceError(str(exc), ErrorSeverity.critical)
        if not g.connected():
            raise SequenceError('X-ray source not connected', ErrorSeverity.fatal)
        if self.level.lower() == 'open':
            g.shutter_open()
            logger.info('Shutter is now open.')
        elif self.level.lower() == 'close':
            g.shutter_close()
            logger.info('Shutter is now closed.')
        else:
            raise SequenceError('Invalid shutter state: ' + self.level, ErrorSeverity.fatal)
    def simulate(self, credo, prevval, variables):
        logger.info('Simulating: setting shutter to ' + self.level)

class SeqCommandChangeSample(SeqCommand):
    command = 'sample'
    cmd_regex = 'sample\s+(?P<title>.*)'
    title = ''
    _arguments = ['title']
    def execute(self, credo, prevval, variables):
        self._kill = False
        try:
            credo.subsystems['Samples'].set(self.title)
        except Exception as exc:
            raise SequenceError(str(exc), ErrorSeverity.critical)
        logger.info('Sample %s selected. Now moving motors.' % (self.title))
        credo.subsystems['Samples'].moveto(blocking=self._handler)

    def _handler(self):
        self.limited_emit('pulse', 'Moving sample %s into the beam' % self.title)
        return self._kill
    def simulate(self, credo, prevval, variables):
        logger.info('Simulating: changing sample to ' + self.title)

class SeqCommandMoveMotor(SeqCommand):
    command = 'moveto'
    cmd_regex = r'moveto\s+(?P<motor>\w+)\s+(?P<to>' + RE_FLOAT_OR_EXPRESSION + ')'
    motor = ''
    to = 0
    _arguments = ['motor', 'to']
    def execute(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        self._kill = False
        try:
            motor = credo.subsystems['Motors'].get(self.motor)
            motor.moveto(float(self.to))
        except Exception as exc:
            raise SequenceError(str(exc), ErrorSeverity.critical)
        logger.info('Moving motor %s to %f.' % (str(motor), float(self.to)))
        credo.subsystems['Motors'].wait_for_idle(self._handler)
        if self._kill:
            raise KillException()
    def _handler(self):
        self.limited_emit('pulse', 'Moving motor %s' % self.motor)
        return self._kill
    def simulate(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        logger.info('Simulating: moving motor ' + self.motor + ' to absolute position ' + str(self.to))

class SeqCommandMoverelMotor(SeqCommand):
    command = 'moverel'
    cmd_regex = r'moverel\s+(?P<motor>\w+)\s+(?P<to>' + RE_FLOAT_OR_EXPRESSION + ')'
    motor = ''
    to = 0
    _arguments = ['motor', 'to']
    def execute(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        self._kill = False
        try:
            motor = credo.subsystems['Motors'].get(self.motor)
            motor.moverel(float(self.to))
        except Exception as exc:
            raise SequenceError(str(exc), ErrorSeverity.critical)
        credo.subsystems['Motors'].wait_for_idle(self._handler)
        if self._kill:
            raise KillException()
    def _handler(self):
        self.limited_emit('pulse', 'Moving motor %s' % self.motor)
        return self._kill
    def simulate(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        logger.info('Simulating: moving motor ' + self.motor + ' to relative position ' + str(self.to))

class SeqCommandLabel(SeqCommand):
    command = 'label'
    cmd_regex = r'label\s+(?P<label>\w+)'
    label = ''
    _arguments = ['label']
    def execute(self, credo, prevval, variables):
        return

class SeqCommandJump(SeqCommand):
    command = 'goto'
    cmd_regex = r'goto\s+(?P<label>\w+)'
    label = ''
    _arguments = ['label']
    def execute(self, credo, prevval, variables):
        raise JumpException(self.label, setstack=False)

class SeqCommandJumpSub(SeqCommand):
    command = 'gosub'
    cmd_regex = r'gosub\s+(?P<label>\w+)'
    label = ''
    _arguments = ['label']
    def execute(self, credo, prevval, variables):
        raise JumpException(self.label, setstack=True)


class SeqCommandJumpTrue(SeqCommand):
    command = 'goif'
    cmd_regex = r'goif\s+(?P<label>\w+)'
    label = ''
    _arguments = ['label']
    def execute(self, credo, prevval, variables):
        if prevval:
            raise JumpException(self.label, setstack=False)
        else:
            return False

class SeqCommandJumpSubTrue(SeqCommand):
    command = 'gosubif'
    cmd_regex = r'gosubif\s+(?P<label>\w+)'
    label = ''
    _arguments = ['label']
    def execute(self, credo, prevval, variables):
        if prevval:
            raise JumpException(self.label, setstack=True)
        else:
            return False


class SeqCommandJumpFalse(SeqCommand):
    command = 'goifnot'
    cmd_regex = r'goifnot\s+(?P<label>\w+)'
    label = ''
    _arguments = ['label']
    def execute(self, credo, prevval, variables):
        if not prevval:
            raise JumpException(self.label, setstack=False)
        else:
            return False

class SeqCommandJumpSubFalse(SeqCommand):
    command = 'gosubifnot'
    cmd_regex = r'gosubifnot\s+(?P<label>\w+)'
    label = ''
    _arguments = ['label']
    def execute(self, credo, prevval, variables):
        if not prevval:
            raise JumpException(self.label, setstack=True)
        else:
            return False


class SeqCommandReturn(SeqCommand):
    command = 'return'
    cmd_regex = r'return'
    def execute(self, credo, prevval, variables):
        raise JumpException(None)

class SeqCommandWithWait(SeqCommand):
    def execute_command(self, credo, prevval, variables, simulate=False):
        self._parse_expressions(credo, prevval, variables)
        if simulate:
            result = self.simulate(credo, prevval, variables)
            self.emit('return', result, 'OK', None)
        else:
            self._prepare(credo, prevval, variables)
    def _prepare(self, credo, prevval, variables):
        pass
    def _start_waiting(self, delay, interval=500):
        self._kill = False
        self._starttime = time.time()
        self._endtime = self._starttime + float(delay)
        GLib.timeout_add(interval, self._idle_func)
    def _end_of_waiting(self, normal_end=True):
        if normal_end:
            self.emit('return', None, 'OK', None)
        else:
            self.emit('return', None, 'KILL', None)
    def _idle_worker(self):
        pass
    def _idle_func(self):
        if self._kill:
            self._end_of_waiting(normal_end=False)
            return False
        if (time.time() > self._endtime):
            self._end_of_waiting(normal_end=True)
            return False
        else:
            self._idle_worker()
            return True

class SeqCommandWait(SeqCommandWithWait):
    command = 'sleep'
    cmd_regex = r'sleep\s+(?P<timeout>' + RE_FLOAT_OR_EXPRESSION + ')'
    timeout = 1
    _arguments = ['timeout']
    def simulate(self, credo, prevval, variables):
        logger.info('Simulating: waiting ' + str(self.timeout) + ' seconds')
    def _prepare(self, credo, prevval, variables):
        self._start_waiting(self.timeout, 500)

class SeqCommandExpose(SeqCommandWithWait):
    command = 'expose'
    cmd_regex = r'expose\s+(?P<exptime>' + RE_FLOAT_OR_EXPRESSION + ')\s+(?P<do_datareduction>' + RE_BOOL + '?)'
    exptime = 1
    do_datareduction = False
    _arguments = ['exptime', 'do_datareduction']
    def _prepare(self, credo, prevval, variables):
        self.do_datareduction = _parse_bool(self.do_datareduction)
        self._kill = None
        self.credo = credo
        sse = credo.subsystems['Exposure']
        credo.subsystems['Files'].filebegin = 'crd'
        self._conn = sse.connect('exposure-end', self._on_end)
        self._imgrecvconn = sse.connect('exposure-image', self._on_image, credo.subsystems['DataReduction'])
        self._failconn = sse.connect('exposure-fail', self._on_fail)
        sse.exptime = float(self.exptime)
        sse.nimages = 1
        fsn = sse.start(write_nexus=True)
        logger.info('Started exposure of FSN #%d.' % fsn)
        self._start_waiting(sse.exptime, 500)
    def _idle_worker(self):
        self.limited_emit('progress', 'Exposing. Time left: %.2f sec.' % (float(self.exptime) - (time.time() - self._starttime)), (time.time() - self._starttime) / float(self.exptime))
    def break_execution(self):
        self._kill = True
        self.credo.subsystems['Exposure'].kill()
    def _on_end(self, sse, status):
        sse.disconnect(self._conn)
        sse.disconnect(self._imgrecvconn)
        sse.disconnect(self._failconn)
        self._conn = None
        self._imgrecvconn = None
        self._failconn = None
        self._kill = not status
        if hasattr(self, '_failmsg'):
            self.emit('return', SequenceError(self._failmsg), 'FAIL', None)
        else:
            SeqCommandWithWait._end_of_waiting(self, status)
    def _on_image(self, sse, exposure, ssdr):
        if self.do_datareduction:
            logger.info('Running data reduction on ' + str(exposure.header))
            ssdr.reduce(exposure['FSN'])
    def _on_fail(self, sse, errmsg):
        self._failmsg = errmsg
    def simulate(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        logger.info('Simulating: exposing for ' + str(self.exptime) + ' seconds')
    def _end_of_waiting(self, normal_end=True):
        # do nothing, we still have to wait for SubSystemExposure to emit the exposure-end signal
        pass

class SeqCommandSet(SeqCommand):
    command = 'set'
    cmd_regex = r'set\s+(?P<varname>\w+)\s+(?P<expression>.*)'
    varname = ''
    expression = ''
    _arguments = ['varname', 'expression']
    def execute(self, credo, prevval, variables):
        variables[self.varname] = eval(self.expression.replace('§', '(' + str(prevval) + ')'), globals(), variables)
        logger.debug('Set %s to %s' % (self.varname, variables[self.varname]))
        return True

class SeqCommandMath(SeqCommand):
    command = 'math'
    cmd_regex = r'math\s+(?P<expression>.*)'
    expression = ''
    _arguments = ['expression']
    def execute(self, credo, prevval, variables):
        return eval(self.expression.replace('§', '(' + str(prevval) + ')'), globals(), variables)

class SeqCommandVacuum(SeqCommand):
    command = 'wait_vacuum'
    cmd_regex = r'wait_vacuum\s+(?P<pressure>' + RE_FLOAT_OR_EXPRESSION + ')'
    pressure = ''
    _arguments = ['pressure']
    def execute(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        self._kill = False
        credo.subsystems['Equipments'].get('vacgauge').wait_for_vacuum(float(self.pressure), lambda :self._handler(credo))
        if self._kill:
            raise KillException()
        return True
    def _handler(self, credo):
        self.limited_emit('pulse', 'Waiting for vacuum <%.4f mbar. Now: %.4f mbar.' % (float(self.pressure), credo.subsystems['Equipments'].get('vacgauge').readout()))
        return self._kill
    def simulate(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        logger.info('Simulating: waiting until vacuum becomes better than ' + str(self.pressure) + ' mbar')

class SeqCommandBreakpoint(SeqCommand):
    command = 'breakpoint'
    cmd_regex = r'breakpoint'
    def execute(self, credo, prevval, variables):
        raise KillException('breakpoint')

class SeqCommandBreakOnFlag(SeqCommand):
    command = 'breakonflag'
    cmd_regex = r'breakonflag\s+(?P<flag>.+)?'
    def execute(self, credo, prevval, variables):
        raise KillException('breakonflag', self.flag)

class SeqCommandEnd(SeqCommand):
    command = 'end'
    cmd_regex = r'end'
    def execute(self, credo, prevval, variables):
        raise KillException()

class SeqCommandSetTemp(SeqCommand):
    command = 'set_temp'
    cmd_regex = r'set_temp\s+(?P<setpoint>' + RE_FLOAT_OR_EXPRESSION + ')'
    setpoint = ''
    _arguments = ['setpoint']
    def execute(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        logger.info('Setting temperature to ' + str(self.setpoint) + ' C')
        credo.get_equipment('haakephoenix').set_setpoint(float(self.setpoint), verify=True)
    def simulate(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        logger.info('Simulating: setting temperature to ' + str(self.setpoint) + ' C')

class SeqCommandWaitTemp(SeqCommand):
    command = 'wait_temp'
    cmd_regex = r'wait_temp\s+(?P<time>' + RE_FLOAT_OR_EXPRESSION + ')\s+(?P<delta>' + RE_FLOAT_OR_EXPRESSION + ')'
    time = ''
    delta = ''
    _arguments = ['time', 'delta']
    def execute(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        self._kill = False
        self._is_in_delta = False
        self._in_delta_since = 0
        self.phoenix = credo.get_equipment('haakephoenix')
        self.setpoint = self.phoenix.get_setpoint()
        self.phoenix.wait_for_temperature(float(self.time), float(self.delta), alternative_breakfunc=self._handler)
        logger.info('Waiting until temperature is stable at %.2f C for at least %.2f seconds.' % (self.setpoint, float(self.time)))
    def _handler(self):
        if not self._is_in_delta and (abs(self.phoenix.get_temperature() - self.setpoint) < float(self.delta)):
            self._is_in_delta = True
            self._in_delta_since = time.time()
        elif (abs(self.phoenix.get_temperature() - self.setpoint) >= float(self.delta)):
            self._is_in_delta = False
        if self._is_in_delta:
            t = time.time()
            self.limited_emit('progress', 'Temperature stable at %.2f C. Waiting for %.2f secs.' % (self.setpoint, float(self.time) - (t - self._in_delta_since)),
                              (time.time() - self._in_delta_since) / float(self.time))
        else:
            self.limited_emit('pulse', 'Waiting for temperature stability. Temperature is at: %.2f C' % self.phoenix.get_temperature())
        return self._kill
    def simulate(self, credo, prevval, variables):
        self._parse_expressions(credo, prevval, variables)
        logger.info('Simulating: waiting until temperature is nearer to the setpoint than ' + str(self.delta) + ' in the interval of ' + str(self.time) + ' seconds')

class SeqCommandStartStopCirculator(SeqCommand):
    command = 'circulator'
    cmd_regex = r'circulator\s+(?P<state>(start|stop))'
    state = ''
    _arguments = ['state']
    def execute(self, credo, prevval, variables):
        if self.state.lower() == 'start':
            credo.get_equipment('haakephoenix').start_circulation()
        elif self.state.lower() == 'stop':
            credo.get_equipment('haakephoenix').stop_circulation()
        else:
            raise SequenceError('Invalid circulator state: ' + self.state)
    def simulate(self, credo, prevval, variables):
        logger.info('Simulating: circulator ' + self.state)


class SequenceInterpreter(GObject.GObject):
    __gsignals__ = {'line':(GObject.SignalFlags.RUN_FIRST, None, (int,)),
                    'cmdprogress':(GObject.SignalFlags.RUN_FIRST, None, (str, float)),
                    'cmdpulse':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    }
    respect_breakpoints = GObject.property(type=bool, default=False, blurb='Break at breakpoints')
    break_on_flags = GObject.property(type=object, blurb='Break when these flags are set')
    pause = GObject.property(type=bool, default=False, blurb='Pause execution: do not start next command if this flag is set.')
    def __init__(self, credo, script):
        GObject.GObject.__init__(self)
        self.break_on_flags = set()
        self.credo = credo
        cmd_classes = [cls for cls in SeqCommand.__subclasses__()]
        newclasses = cmd_classes
        while newclasses:
            newclasses = [cls for cls in reduce(lambda a, b:a + b, [k.__subclasses__() for k in cmd_classes]) if cls not in cmd_classes]
            cmd_classes.extend(newclasses)
        self._commands = [cls() for cls in cmd_classes if cls.command is not None]
        logger.debug('Known sequence commands: ' + ', '.join(c.command for c in self._commands))
        self._script = [x.strip() for x in script.split('\n')]
        self._init_exec()
    def _init_exec(self):
        self._idx = 0
        self._vars = {}
        self._prevval = None
        self._callstack = []
        self._cmdconn = []
        self._currentcommand = None
        self._break = False
        self._simulation = False
    def stop(self):
        if self._currentcommand is not None:
            self._currentcommand.break_execution()
        self._break = True
    def do_end(self, endstatus):
        if endstatus:
            logger.info('Sequence ended normally.')
        else:
            logger.info('Sequence ended on user break.')
    def do_fail(self, status):
        logger.error('Sequence failed: %s' % status)
    def _command_return(self, command, result, status, auxresult):
        for c in self._cmdconn:
            command.disconnect(c)
        self._cmdconn = []
        if status == 'KILL':
            if isinstance(auxresult, tuple):
                if not auxresult:
                    self.emit('end', False)
                elif auxresult[0] == 'breakpoint' and self.respect_breakpoints:
                    self.emit('end', False)
                elif auxresult[0] == 'breakonflag' and auxresult[1] in self.break_on_flags:
                    self.emit('end', False)
                else:
                    status = 'OK'
                    result = self._prevval
            else:
                self.emit('end', False)
        if status == 'OK':
            self._prevval = result
            logger.debug('Command returned: ' + str(self._prevval))
            logger.debug('Variables: ' + str(self._vars))
            # command finished OK, we need to start the next command.
            self._idx += 1
            self.execute_next_command(result)
        elif status == 'FAIL':
            # a failure happened, end of sequence
            self.emit('fail', 'Command ' + command.command + ' failed with: ' + str(result))
        elif status == 'JUMP':
            # we need to jump. The label to jump is in 'result', while 'auxresult' is a boolean, controlling if we have to save the stack.
            logger.debug('Jump requested to label: ' + str(result))
            logger.debug('Call stack before jump is: ' + str(self._callstack))
            if result is None:
                try:
                    # return to the previous point.
                    self._idx = self._callstack.pop() + 1
                    logger.debug('Going back to line ' + str(self._idx))
                except:
                    self.emit('fail', 'Stack underflow on line %d: %s' % (self._idx + 1, self._script[self._idx]))
            else:
                if auxresult:
                    logger.debug('saving line #%d to call stack.' % self._idx)
                    self._callstack.append(self._idx)
                self._idx = self._findlabel(result)
                logger.debug('Label is at line: ' + str(self._idx))
            logger.debug('Call stack after jump is: ' + str(self._callstack))
            self._prevval = None
            self.execute_next_command(self._prevval)
    def execute_next_command(self, prevval=None):
        if self._idx >= len(self._script):
            self.emit('end', True)
            return
        if self._break:
            self.emit('end', False)
            return
        self.emit('line', self._idx)
        # find the command to execute.
        clis = [c for c in self._commands if c.match(self._script[self._idx])]
        if not clis:
            self.emit('fail', 'Unknown command in line %d: %s' % (self._idx + 1, self._script[self._idx]))
        elif len(clis) > 1:
            self.emit('Ambiguous command in line %d: %s' % (self._idx + 1, self._script[self._idx]))
        else:
            logger.debug('Command is: ' + clis[0].__class__.__name__)
            self._currentcommand = clis[0]
            self._cmdconn = [self._currentcommand.connect('pulse', lambda cmd, text: self.emit('cmdpulse', text)),
                             self._currentcommand.connect('progress', lambda cmd, text, proportion: self.emit('cmdprogress', text, proportion)),
                             self._currentcommand.connect('return', self._command_return), ]
            GLib.idle_add(self._currentcommand.execute_command, self.credo, prevval, self._vars, self._simulation)
    def execute(self, simulation=False):
        self._init_exec()
        logger.info('Starting execution of program.')
        self.execute_next_command(None)
    def _findlabel(self, labelname):
        scl = SeqCommandLabel()
        labels = [i for i in range(len(self._script)) if (scl.match(self._script[i]) and (scl.label == labelname))]
        if not labels:
            raise SequenceSyntaxError('Unknown label: ' + labelname)
        elif len(labels) > 1:
            raise SequenceSyntaxError('Label %s defined multiple times.' % labelname)
        else:
            return labels[0]
    def do_line(self, lineno):
        logger.debug('Executing line %d: %s' % (lineno, self._script[lineno]))
        pass

class SAXSSequence(ToolDialog):
    _filename = 'untitled.aseq'
    _changed = False
    def __init__(self, credo, title='SAXS Sequence'):
        # ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_SAVE, self.RESPONSE_SAVE, Gtk.STOCK_OPEN, self.RESPONSE_OPEN, Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))

        self.sequence = Gtk.ListStore(GObject.TYPE_STRING,  # element string
                                      GObject.TYPE_OBJECT,  # element object
                                      )
        vb = self.get_content_area()
        self._main_toolbar = Gtk.Toolbar()
        vb.pack_start(self._main_toolbar, False, False, 0)
        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('document-new', Gtk.IconSize.SMALL_TOOLBAR), label='New sequence')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._new_sequence)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('document-open', Gtk.IconSize.SMALL_TOOLBAR), label='Open sequence')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._open_sequence)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('document-save', Gtk.IconSize.SMALL_TOOLBAR), label='Save sequence')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._save_sequence)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('document-save-as', Gtk.IconSize.SMALL_TOOLBAR), label='Save sequence as')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._saveas_sequence)

        sep = Gtk.SeparatorToolItem()
        self._main_toolbar.insert(sep, -1)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('edit-cut', Gtk.IconSize.SMALL_TOOLBAR), label='Cut')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._cut_selection)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('edit-copy', Gtk.IconSize.SMALL_TOOLBAR), label='Copy')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._copy_selection)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('edit-paste', Gtk.IconSize.SMALL_TOOLBAR), label='Paste')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._paste_selection)

        sep = Gtk.SeparatorToolItem()
        self._main_toolbar.insert(sep, -1)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('edit-undo', Gtk.IconSize.SMALL_TOOLBAR), label='Undo')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._undo_changes)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('edit-redo', Gtk.IconSize.SMALL_TOOLBAR), label='Redo')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._redo_changes)

        sep = Gtk.SeparatorToolItem()
        self._main_toolbar.insert(sep, -1)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('media-playback-start', Gtk.IconSize.SMALL_TOOLBAR), label='Execute sequence')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._start_sequence)

        tb = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name('media-playback-stop', Gtk.IconSize.SMALL_TOOLBAR), label='Stop sequence')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._stop_sequence)

        tb = Gtk.ToggleToolButton()
        tb.set_icon_widget(Gtk.Image.new_from_icon_name('media-playback-pause', Gtk.IconSize.SMALL_TOOLBAR))
        tb.set_label('Pause after next command')
        self._main_toolbar.insert(tb, -1)
        tb.connect('clicked', self._pause_sequence)

        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, True, True, 0)
        sw = Gtk.ScrolledWindow()
        hb.pack_start(sw, True, True, 0)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._sourcebuffer = GtkSource.Buffer()
        self._sourceview = GtkSource.View(buffer=self._sourcebuffer)
        sw.set_size_request(-1, 400)
        sw.add(self._sourceview)
        self._sourceview.set_show_line_numbers(True)
        self._sourceview.set_show_line_marks(True)
        self._sourceview.set_highlight_current_line(True)
        self._sourceview.set_draw_spaces(GtkSource.DrawSpacesFlags.ALL)
        self._sourceview.override_font(Pango.FontDescription('monospace 12'))
        self._sourceview.set_size_request(-1, 400)
        self._sourceview.set_insert_spaces_instead_of_tabs(True)
        self._sourceview.set_indent_width(4)
        self._sourceview.set_tab_width(4)
        ma = GtkSource.MarkAttributes()
        ma.set_stock_id(Gtk.STOCK_MEDIA_PLAY)
        ma.set_background(Gdk.RGBA(0, 1, 0, 1))
        self._sourceview.set_mark_attributes('Executing', ma, 0)
        self._progressbar = Gtk.ProgressBar()
        vb.pack_start(self._progressbar, False, False, 0)
        self._progressbar.set_no_show_all(True)
        self._interpreter = None
        self._breakpointcb = Gtk.CheckButton(label='Respect breakpoints')
        self._breakpointcb.connect('toggled', lambda cb:((self._interpreter is not None) and (self._interpreter.set_property('respect_breakpoints', cb.get_active()))))
        self.get_action_area().add(self._breakpointcb)
        self._simulatecb = Gtk.CheckButton(label='Just simulate')
        self.get_action_area().add(self._simulatecb)
        self._sourcebuffer_start_tracking_changes()
    def _sourcebuffer_restart_tracking_changes(self):
        self._sourcebuffer_stop_tracking_changes()
        self._sourcebuffer_start_tracking_changes()
    def _sourcebuffer_start_tracking_changes(self):
        self._sbchangeconn = self._sourcebuffer.connect('changed', self._sourcebuffer_stop_tracking_changes)
        self.set_title('Automatic sequence -- ' + os.path.split(self._filename)[-1])
        self._changed = False
    def _sourcebuffer_stop_tracking_changes(self, sb=None):
        self._changed = True
        self.set_title('Automatic sequence -- ' + os.path.split(self._filename)[-1] + '*')
        self._sourcebuffer.disconnect(self._sbchangeconn)
    def on_saveorload(self, what):
        if self._filename == 'untitled.aseq' and what == 'save':
            what = 'saveas'
        if what == 'save':
            self.save_to(self._filename)
            return
        if (not hasattr(self, '_fcd')) and (what in ['saveas', 'load']):
            self._fcd = Gtk.FileChooserDialog('Save automatic sequence to...', self, Gtk.FileChooserAction.SAVE, (Gtk.STOCK_SAVE, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
            ff = Gtk.FileFilter(); ff.set_name('All files (*)'); ff.add_pattern('*'); self._fcd.add_filter(ff)
            ff = Gtk.FileFilter(); ff.set_name('Automatic sequence files (*.aseq)'); ff.add_pattern('*.aseq'); self._fcd.add_filter(ff)
            self._fcd.set_filter(ff)
            if what == 'saveas':
                self._fcd.set_current_name(self._filename)
        if what == 'saveas':
            self._fcd.set_title('Save automatic sequence to...')
            self._fcd.set_action(Gtk.FileChooserAction.SAVE)
            self._fcd.set_do_overwrite_confirmation(True)
            self._fcd.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_SAVE_AS)
        elif what == 'load':
            self._fcd.set_title('Load automatic sequence from...')
            self._fcd.set_action(Gtk.FileChooserAction.OPEN)
            self._fcd.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_OPEN)
        if self._fcd.run() == Gtk.ResponseType.OK:
            filename = self._fcd.get_filename()
            if what in ['save', 'saveas']:
                self.save_to(filename)
            elif what == 'load':
                self.load_from(filename)
        self._fcd.hide()
    def get_script(self):
        return self._sourcebuffer.get_text(self._sourcebuffer.get_start_iter(), self._sourcebuffer.get_end_iter(), True)
    def save_to(self, filename):
        try:
            with open(filename, 'wt') as f:
                f.write(self.get_script())
            self._filename = filename
            self._sourcebuffer_restart_tracking_changes()
        except IOError as ioe:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Could not save program to file ' + filename + '.')
            md.format_secondary_text('Reason: ' + str(ioe))
            md.run()
            md.destroy()
            del md
    def load_from(self, filename):
        try:
            with open(filename, 'rt') as f:
                self._sourcebuffer.set_text(f.read())
            self._filename = filename
            self._sourcebuffer_restart_tracking_changes()
        except (IOError, ValueError) as err:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Could not load program from file ' + filename + '.')
            md.format_secondary_text('Reason: ' + str(err))
            md.run()
            md.destroy()
            del md
    def _do_line(self, interp, lineno):
        it = self._sourcebuffer.get_iter_at_line(lineno)
        self._sourcebuffer.remove_source_marks(self._sourcebuffer.get_start_iter(), self._sourcebuffer.get_end_iter(), 'Executing')
        self._sourcebuffer.create_source_mark('Line #%d' % lineno, 'Executing', it)
        self._sourceview.scroll_to_iter(it, 0, False, 0, 0)
        self._sourcebuffer.place_cursor(it)
        self._progressbar.hide()
    def _do_progress(self, interp, text, fraction=None):
        self._progressbar.show_now()
        self._progressbar.set_show_text(True)
        self._progressbar.set_text(text)
        if fraction is None:
            self._progressbar.pulse()
        else:
            self._progressbar.set_fraction(fraction)
    def _new_sequence(self, toolbutton):
        pass
    def _open_sequence(self, toolbutton):
        self.on_saveorload('load')
    def _save_sequence(self, toolbutton):
        self.on_saveorload('save')
    def _saveas_sequence(self, toolbutton):
        self.on_saveorload('saveas')
    def _cut_selection(self, toolbutton):
        self._sourcebuffer.cut_clipboard(Gtk.Clipboard.get_for_display(Gdk.Display.get_default(), Gdk.SELECTION_PRIMARY), True)
    def _copy_selection(self, toolbutton):
        self._sourcebuffer.cut_clipboard(Gtk.Clipboard.get_for_display(Gdk.Display.get_default(), Gdk.SELECTION_PRIMARY))
    def _paste_selection(self, toolbutton):
        self._sourcebuffer.paste_clipboard(Gtk.Clipboard.get_for_display(Gdk.Display.get_default(), Gdk.SELECTION_PRIMARY), None, True)
    def _undo_changes(self, toolbutton):
        self._sourcebuffer.undo()
    def _redo_changes(self, toolbutton):
        self._sourcebuffer.redo()
    def _cleanup_after_sequence(self):
        for c in self._interpreter_conns:
            self._interpreter.disconnect(c)
        self._interpreter_conns = []
        self._progressbar.hide()
        self.get_action_area().foreach(lambda b, state:b.set_sensitive(state), True)
        self._sourcebuffer.remove_source_marks(self._sourcebuffer.get_start_iter(), self._sourcebuffer.get_end_iter(), 'Executing')
        self._sourceview.set_editable(True)
        self._sourceview.set_cursor_visible(True)
        del self._interpreter
        self._interpreter = None
    def _do_end(self, interpreter, endstatus):
        if endstatus:
            endmsg = 'Sequence finished normally.'
        else:
            endmsg = 'User break!'
        md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, endmsg)
        md.run()
        md.destroy()
        del md
        self._cleanup_after_sequence()
    def _do_fail(self, interpreter, errormsg):
        md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Error while running sequence.')
        md.format_secondary_text('Reason: ' + str(errormsg))
        md.run()
        md.destroy()
        del md
        self._cleanup_after_sequence()
    def _start_sequence(self, toolbutton):
        if self._interpreter is not None:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Sequence is already running.')
            md.run()
            md.destroy()
            del md
            return
        self._interpreter = SequenceInterpreter(self.credo, self.get_script())
        self._interpreter_conns = [self._interpreter.connect('line', self._do_line),
                                   self._interpreter.connect('cmdpulse', self._do_progress),
                                   self._interpreter.connect('cmdprogress', self._do_progress),
                                   self._interpreter.connect('end', self._do_end),
                                   self._interpreter.connect('fail', self._do_fail),
                                   ]
        self._sourceview.set_editable(False)
        self._sourceview.set_cursor_visible(False)
        self.get_action_area().foreach(lambda b, state:b.set_sensitive(state), False)
        # self._main_toolbar.foreach(lambda b: b.set_sensitive(False))

        self._breakpointcb.set_sensitive(True)
        self._interpreter.set_property('respect-breakpoints', self._breakpointcb.get_active())
        self._interpreter.execute(self._simulatecb.get_active())
    def _pause_sequence(self, toolbutton):
        pass
    def _stop_sequence(self, toolbutton):
        if self._interpreter is None:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Sequence is not running.')
            md.run()
            md.destroy()
            del md
            return
        self._interpreter.stop()

    def do_response(self, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            if self._changed:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, 'Sequence script has been modified, and will be lost unless saved. Do you want to save it?')
                if md.run() == Gtk.ResponseType.YES:
                    self.on_saveorload('save')
                else:
                    pass
                md.destroy()
                del md
            self.destroy()
        else:
            raise NotImplementedError()
