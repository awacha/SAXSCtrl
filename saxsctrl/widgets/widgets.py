from gi.repository import Gtk
from gi.repository import GObject
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
import calendar
import datetime
import dateutil.parser
import sastool


class ToolDialog(Gtk.Window):
    __gtype_name__ = "SAXSCtrl_ToolDialog"
    __gsignals__ = {'response':(GObject.SignalFlags.RUN_FIRST, None, (int,))}
    def __init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        Gtk.Window.__init__(self)
        self.set_title(title)
        self.credo = credo
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vb)
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vb.pack_start(self._content, True, True, 0)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(sep, False, True, 0)
        self._action = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        self._action.set_layout(Gtk.ButtonBoxStyle.END)
        vb.pack_start(self._action, False, True, 0)
        self._responsewidgets = {}
        for i in range(len(buttons) / 2):
            respid = buttons[i * 2 + 1]
            self._responsewidgets[respid] = Gtk.Button(stock=buttons[i * 2])
            self._action.add(self._responsewidgets[respid])
            self._responsewidgets[respid].connect('clicked', lambda b, respid:self.emit('response', respid), buttons[i * 2 + 1])
    def get_content_area(self):
        return self._content
    def get_action_area(self):
        return self._action
    def set_response_sensitive(self, respid, sensitive):
        self._responsewidgets[respid].set_sensitive(sensitive)
    def get_widget_for_response(self, respid):
        return self._responsewidgets[respid]
    def do_response(self, respid):
        logger.debug('Destroying a ToolDialog.')
        if self.in_destruction():
            logger.warn('ToolDialog already being destroyed.')
        self.destroy()
        logger.debug('End of destroying a ToolDialog.')
    def do_destoy(self):
        logger.debug('Called ToolDialog.do_destroy()')

class DateEntry(Gtk.Box):
    __gtype_name__ = 'SAXSCtrl_DateEntry'
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_LAST, None, ())}
    def __init__(self, **kwargs):
        Gtk.Box.__init__(self, **kwargs)
        boxdate = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(boxdate, True, True, 0)
        boxtime = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(boxtime, True, True, 0)
        self._yearspin = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=0, lower=-9999, upper=9999, step_increment=1, page_increment=10), digits=0)
        self._yearspin.connect('changed', self._year_changed)
        self._monthspin = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=1, lower=1, upper=12, step_increment=1, page_increment=10), digits=0)
        self._monthspin.connect('changed', self._month_changed)
        self._monthspin.connect('wrapped', self._month_wrapped)
        self._monthspin.set_wrap(True)
        self._dayspin = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=1, lower=1, upper=31, step_increment=1, page_increment=10), digits=0)
        self._dayspin.connect('changed', self._day_changed)
        self._dayspin.connect('wrapped', self._day_wrapped)
        self._dayspin.set_wrap(True)
        self._hourspin = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=0, lower=0, upper=23, step_increment=1, page_increment=10), digits=0)
        self._hourspin.connect('changed', self._hour_changed)
        self._hourspin.connect('wrapped', self._hour_wrapped)
        self._hourspin.set_wrap(True)
        self._minutespin = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=0, lower=0, upper=59, step_increment=1, page_increment=10), digits=0)
        self._minutespin.connect('changed', self._minute_changed)
        self._minutespin.connect('wrapped', self._minute_wrapped)
        self._minutespin.set_wrap(True)
        self._secondspin = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=0, lower=0, upper=59, step_increment=1, page_increment=10), digits=0)
        self._secondspin.connect('changed', self._second_changed)
        self._secondspin.connect('wrapped', self._second_wrapped)
        self._secondspin.set_wrap(True)
        boxdate.pack_start(self._yearspin, True, True, 0)
        boxdate.pack_start(self._monthspin, True, True, 0)
        boxdate.pack_start(self._dayspin, True, True, 0)
        boxtime.pack_start(self._hourspin, True, True, 0)
        boxtime.pack_start(self._minutespin, True, True, 0)
        boxtime.pack_start(self._secondspin, True, True, 0)
        self.show_all()
    def _second_wrapped(self, sb):
        if sb.get_value_as_int() == 0:
            self._minutespin.spin(Gtk.SpinType.STEP_FORWARD, 1)
        else:
            self._minutespin.spin(Gtk.SpinType.STEP_BACKWARD, 1)
    def _minute_wrapped(self, sb):
        if sb.get_value_as_int() == 0:
            self._hourspin.spin(Gtk.SpinType.STEP_FORWARD, 1)
        else:
            self._hourspin.spin(Gtk.SpinType.STEP_BACKWARD, 1)
    def _hour_wrapped(self, sb):
        if sb.get_value_as_int() == 0:
            self._dayspin.spin(Gtk.SpinType.STEP_FORWARD, 1)
        else:
            self._dayspin.spin(Gtk.SpinType.STEP_BACKWARD, 1)
    def _day_wrapped(self, sb):
        if sb.get_value_as_int() == 0:
            self._monthspin.spin(Gtk.SpinType.STEP_FORWARD, 1)
        else:
            self._monthspin.spin(Gtk.SpinType.STEP_BACKWARD, 1)
    def _month_wrapped(self, sb):
        if sb.get_value_as_int() == 0:
            self._yearspin.spin(Gtk.SpinType.STEP_FORWARD, 1)
        else:
            self._yearspin.spin(Gtk.SpinType.STEP_BACKWARD, 1)
    def _year_changed(self, sb):
        self._set_limits()
        self.emit('changed')
    def _month_changed(self, sb):
        self._set_limits()
        self.emit('changed')
    def _day_changed(self, sb):
        self._set_limits()
        self.emit('changed')
    def _hour_changed(self, sb):
        self._set_limits()
        self.emit('changed')
    def _minute_changed(self, sb):
        self._set_limits()
        self.emit('changed')
    def _second_changed(self, sb):
        self._set_limits()
        self.emit('changed')
    def _set_limits(self):
        if (self._monthspin.get_value_as_int() == 2):
            if calendar.isleap(self._yearspin.get_value_as_int()):
                self._dayspin.set_range(1, 29)
            else:
                self._dayspin.set_range(1, 28)
        elif self._monthspin.get_value_as_int() in [1, 3, 5, 7, 8, 10, 12]:
            self._dayspin.set_range(1, 31)
        else:
            self._dayspin.set_range(1, 30)
    def get_datetime(self):
        return datetime.datetime(self._yearspin.get_value_as_int(),
                                 self._monthspin.get_value_as_int(),
                                 self._dayspin.get_value_as_int(),
                                 self._hourspin.get_value_as_int(),
                                 self._minutespin.get_value_as_int(),
                                 self._secondspin.get_value_as_int())
    def get_epoch(self):
        return float(self.get_datetime().strftime('%s.%f'))
    def set_datetime(self, dt):
        if isinstance(dt, basestring):
            dt = dateutil.parser.parse(dt)
        elif isinstance(dt, float) or isinstance(dt, int):
            dt = datetime.datetime.fromtimestamp(dt)
        elif isinstance(dt, datetime.datetime):
            pass
        else:
            raise ValueError('Cannot parse date: invalid type ' + str(type(dt)))
        self._yearspin.set_value(dt.year)
        self._monthspin.set_value(dt.month)
        self._dayspin.set_value(dt.day)
        self._hourspin.set_value(dt.hour)
        self._minutespin.set_value(dt.minute)
        self._secondspin.set_value(dt.second)

class ErrorValueEntry(Gtk.Box):
    __gtype_name__ = 'SAXSCtrl_ErrorValueEntry'
    __gsignals__ = {'value-changed':(GObject.SignalFlags.RUN_LAST, None, ()),
                  'changed':(GObject.SignalFlags.RUN_LAST, None, ())}
    def __init__(self, adjustment_nominal=None, adjustment_error=None, climb_rate=None, digits=None):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL)
        kwargs = {}
        if climb_rate is not None:
            kwargs['climb_rate'] = climb_rate
        if digits is not None:
            kwargs['digits'] = digits
        self._valsb = Gtk.SpinButton(adjustment=adjustment_nominal, **kwargs)
        self._errsb = Gtk.SpinButton(adjustment=adjustment_error, **kwargs)
        self._valsb.set_value(adjustment_nominal.get_value())
        self._errsb.set_value(adjustment_error.get_value())
        self.pack_start(self._valsb, True, True, 0)
        self.pack_start(Gtk.Label(label=u'\xb1'), False, False, 2)
        self.pack_start(self._errsb, True, True, 0)
        self._valsb.connect('value-changed', self._on_spinbutton_value_changed)
        self._errsb.connect('value-changed', self._on_spinbutton_value_changed)
        self._valsb.connect('changed', self._on_spinbutton_changed)
        self._errsb.connect('changed', self._on_spinbutton_changed)

    def _on_spinbutton_value_changed(self, spinbutton):
        self.emit('value-changed')

    def _on_spinbutton_changed(self, spinbutton):
        self.emit('changed')

    def set_digits(self, digits):
        self._valsb.set_digits(digits)
        self._Errsb.set_digits(digits)

    def set_value(self, value):
        if isinstance(value, sastool.ErrorValue):
            self._valsb.set_value(value.val)
            self._errsb.set_value(value.err)
        else:
            self._valsb.set_value(value)
            self._errsb.set_value(0)

    def get_value(self):
        return sastool.ErrorValue(self._valsb.get_value(), self._errsb.get_value())
