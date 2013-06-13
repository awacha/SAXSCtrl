from gi.repository import Gtk
from gi.repository import GObject
from .widgets import ToolDialog
from .samplesetup import SampleSelector
from ..hardware.instruments import genix
import ConfigParser

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class SequenceElement(GObject.GObject):
    __gsignals__ = {'finished':(GObject.SignalFlags.RUN_FIRST, None, (bool, object)),  # emitted when the task is finished. True if OK, False if break.
                    }
    finished = GObject.property(type=bool, default=True)
    def __init__(self):
        GObject.GObject.__init__(self)
        self.finished = True
    def execute(self, credo):
        raise NotImplementedError()
    def estimate_time(self, credo):
        return 0
    def reset(self):
        return True
    def break_operation(self, credo):
        self.emit('finished', False, None)
        return True
    def __str__(self):
        raise NotImplementedError()
    def to_configparser(self, cp, sectionname):
        if cp.has_section(sectionname):
            cp.remove_section(sectionname)
        cp.add_section(sectionname)
        cp.set(sectionname, 'type', self.__class__.__name__)
    @classmethod
    def from_configparser(cls, cp, sectionname):
        if not cp.has_section(sectionname):
            raise ValueError('No section %s in configuration file.' % sectionname)
        if not cp.has_option(sectionname, 'type'):
            raise ValueError('No type field in section %s of the configuration file.' % (sectionname))
        if cp.get(sectionname, 'type') != cls.__name__:
            raise ValueError('Expected type %s, got %s instead.' % (cls.__name__, cp.get(sectionname, 'type')))
    def get_dialog(self, credo, parent=None):
        dia = Gtk.Dialog('Add/modify element %s' % (self.__class__.__name__.replace('SequenceElement', '')),
                       parent, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                       (Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        return dia
    @classmethod
    def from_dialog(cls, credo, parent=None):
        self = cls()
        self.edit_with_dialog(credo, parent)
        return self
    def edit_with_dialog(self, credo, parent=None):
        dia = self.get_dialog(credo, parent)
        dia.get_content_area().show_all()
        if dia.run() == Gtk.ResponseType.OK:
            self.update_from_dialog(credo, dia)
        dia.destroy()
        del dia
    def update_from_dialog(self, credo, dia):
        raise NotImplementedError()
    @classmethod
    def new_from_configparser(cls, cp, sectionname):
        if not cp.has_section(sectionname):
            raise ValueError('No section %s in configuration file.' % sectionname)
        if not cp.has_option(sectionname, 'type'):
            raise ValueError('No type field in section %s of the configuration file.' % (sectionname))
        type_ = cp.get(sectionname, 'type')
        for sc in cls.__subclasses__():
            if sc.__name__ == type_:
                return sc.from_configparser(cp, sectionname)
        raise ValueError('Invalid type: ' + type_)
    
class SequenceElementChangeSample(SequenceElement):
    """ChangeSample: change the sample
    
    Selects the selected sample for exposure. Also moves the sample motors to the
    given position.
    """
    def __init__(self, sam='-- UNKNOWN --'):
        SequenceElement.__init__(self)
        self.sample = sam
        self.breaking = False
    def execute(self, credo):
        try:
            self.sample = credo.set_sample(self.sample)
            self._crdconn = credo.connect('idle', self._execute_done)
            credo.moveto_sample(blocking=False)
        except Exception as ex:
            logger.error('Error while changing sample: ' + ex.message)
    def _execute_done(self, credo):
        credo.disconnect(self._crdconn)
        self._crdconn = None
        self.emit('finished', not self.breaking, None)
    def break_operation(self, credo):
        self.breaking = True
        credo.tmcm.motorstop()
    def estimate_time(self, credo):
        return 10
    def __str__(self):
        return 'Change to sample ' + str(self.sample)
    def to_configparser(self, cp, sectionname):
        SequenceElement.to_configparser(self, cp, sectionname)
        cp.set(sectionname, 'sample', self.sample.title)
    @classmethod
    def from_configparser(cls, cp, sectionname):
        super(SequenceElementChangeSample, cls).from_configparser(cp, sectionname)
        return cls(cp.get(sectionname, 'sample'))
    def get_dialog(self, credo, parent=None):
        dia = SequenceElement.get_dialog(self, credo, parent)
        vb = dia.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, True, True, 0)
        
        row = 0
        l = Gtk.Label(label='Sample:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        dia.sample_entry = SampleSelector(credo, autorefresh=False)
        tab.attach(dia.sample_entry, 1, 2, row, row + 1)
        dia.sample_entry.set_sample(self.sample)
        row += 1
        return dia
    def update_from_dialog(self, credo, dia):
        self.sample = dia.sample_entry.get_sample()

        
class SequenceElementExpose(SequenceElement):
    """Expose: make an exposure
    
    Makes an exposure with the given exposure time (seconds).
    """
    def __init__(self, exptime=300):
        SequenceElement.__init__(self)
        self.exptime = exptime
        self.exposure = None
    def execute(self, credo):
        self._credoconn = [credo.connect('exposure-end', self._executefinished),
                         credo.connect('exposure-done', self._exposure_done)]
        self.exposure = None
        credo.set_fileformat('crd')
        credo.expose(self.exptime)
        return True
    def estimate_time(self, credo):
        return self.exptime
    def break_operation(self, credo):
        credo.killexposure()
    def __str__(self):
        return "Expose with 2D detector for %.2f seconds." % self.exptime
    def _exposure_done(self, credo, exposure):
        self.exposure = exposure
    def _executefinished(self, credo, status):
        for c in self._credoconn:
            credo.disconnect(c)
        self._credoconn = None
        self.emit('finished', status, self.exposure)
    def to_configparser(self, cp, sectionname):
        SequenceElement.to_configparser(self, cp, sectionname)
        cp.set(sectionname, 'exptime', self.exptime)
    @classmethod
    def from_configparser(cls, cp, sectionname):
        super(SequenceElementExpose, cls).from_configparser(cp, sectionname)
        return cls(cp.getfloat(sectionname, 'exptime'))
    def get_dialog(self, credo, parent=None):
        dia = SequenceElement.get_dialog(self, credo, parent)
        vb = dia.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, True, True, 0)
        
        row = 0
        l = Gtk.Label(label='Exposure time (sec):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        dia.exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.exptime, 0, 1e6, 1, 10), digits=2)
        tab.attach(dia.exptime_entry, 1, 2, row, row + 1)
        dia.exptime_entry.set_value(self.exptime)
        row += 1
        return dia
    def update_from_dialog(self, credo, dia):
        self.exptime = dia.exptime_entry.get_value()

class SequenceElementGeniXPower(SequenceElement):
    """GeniXPower: adjust the power of the X-ray beam delivery system.
    
    Power states: 'OFF', 'STANDBY' (9 W), 'FULL' (30 W).
    
    DO NOT EVER LET THE BEAM IN 'FULL' MODE HIT THE DETECTOR!
    """
    def __init__(self, to_state='OFF'):
        """Turn the GeniX power to to_state.
        
        to_state can be: 'OFF', 'STANDBY', 'FULL'
        """
        SequenceElement.__init__(self)
        self.to_state = to_state
    def execute(self, credo):
        if self.to_state.upper() == 'OFF':
            credo.genix.do_poweroff()
        elif self.to_state.upper() == 'STANDBY':
            credo.genix.do_standby()
        elif self.to_state.upper() == 'FULL':
            credo.genix.do_rampup()
        self._timeouthandler = GObject.timeout_add(500, self._checkfinished, credo)
    def break_operation(self, credo):
        if hasattr(self, '_timeouthandler'):
            GObject.source_remove(self._timeouthandler)
        self.emit('finished', False, None)
    def estimate_time(self, credo):
        return 0
    def __str__(self):
        return "Set X-ray source power to " + self.to_state.upper()
    def _checkfinished(self, credo):
        ws = credo.genix.whichstate()
        if ((ws == genix.GENIX_FULLPOWER and self.to_state.upper() == 'FULL') or
            (ws == genix.GENIX_STANDBY and self.to_state.upper() == 'STANDBY') or
            (ws == genix.GENIX_POWERDOWN and self.to_state.upper() == 'OFF')):
            # we are finished.
            self.emit('finished', True, self.to_state.upper())
            return False
        elif ((ws == genix.GENIX_GO_FULLPOWER and self.to_state.upper() == 'FULL') or
              (ws == genix.GENIX_GO_STANDBY and self.to_state.upper() == 'STANDBY') or
              (ws == genix.GENIX_GO_POWERDOWN and self.to_state.upper() == 'OFF')):
            # we are going there.
            return True
        else:
            # something else happened, this we consider an error.
            self.emit('finished', False, None)
            return False
    def to_configparser(self, cp, sectionname):
        SequenceElement.to_configparser(self, cp, sectionname)
        cp.set(sectionname, 'to_state', self.to_state)
    @classmethod
    def from_configparser(cls, cp, sectionname):
        super(SequenceElementGeniXPower, cls).from_configparser(cp, sectionname)
        return cls(cp.get(sectionname, 'to_state'))
    def get_dialog(self, credo, parent=None):
        dia = SequenceElement.get_dialog(self, credo, parent)
        vb = dia.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, True, True, 0)
        
        row = 0
        l = Gtk.Label(label='Final state:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        dia.state_entry = Gtk.ComboBoxText()
        for i, state in enumerate(['FULL', 'STANDBY', 'OFF']):
            dia.state_entry.append_text(state)
            if state == self.to_state.upper():
                dia.state_entry.set_active(i)
        tab.attach(dia.state_entry, 1, 2, row, row + 1)
        row += 1
        return dia
    def update_from_dialog(self, credo, dia):
        self.to_state = dia.state_entry.get_active_text()

class SequenceElementLabel(SequenceElement):
    """Label: define a label to jump to.
    
    The label name should be unque. Use of white spaces and non-alphanumeric
    characters and such funny business is discouraged. Label names are case sensitive.
    """
    def __init__(self, id='label'):
        SequenceElement.__init__(self)
        self.id = id
    def execute(self, credo):
        GObject.idle_add(self._finish_execute)
        return True
    def _finish_execute(self):
        self.emit('finished', True, self.id)
        return False
    def estimate_time(self, credo):
        return 0
    def __str__(self):
        return "Label: " + str(self.id)
    def to_configparser(self, cp, sectionname):
        SequenceElement.to_configparser(self, cp, sectionname)
        cp.set(sectionname, 'id', self.id)
    @classmethod
    def from_configparser(cls, cp, sectionname):
        super(SequenceElementLabel, cls).from_configparser(cp, sectionname)
        return cls(cp.get(sectionname, 'id'))
    def get_dialog(self, credo, parent=None):
        dia = SequenceElement.get_dialog(self, credo, parent)
        vb = dia.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, True, True, 0)
        
        row = 0
        l = Gtk.Label(label='Label ID:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        dia.id_entry = Gtk.Entry()
        dia.id_entry.set_text(self.id)
        tab.attach(dia.id_entry, 1, 2, row, row + 1)
        row += 1
        return dia
    def update_from_dialog(self, credo, dia):
        self.id = dia.id_entry.get_text()
    
class SequenceElementLoop(SequenceElement):
    """Loop to a label up to a different number of iterations.
    """
    def __init__(self, targetid='label', nrjumps=1):
        SequenceElement.__init__(self)
        self.targetid = targetid
        self.nrjumps = nrjumps
        self.totaljumps = 0
    def execute(self, credo):
        if self.totaljumps >= self.nrjumps:
            self.reset()
            GObject.idle_add(lambda : self.emit('finished', False) and False)
        else:
            self.totaljumps += 1
            GObject.idle_add(lambda : self.emit('finished', True) and False)
        return True
    def estimate_time(self, credo):
        return 0
    def reset(self):
        self.totaljumps = 0
    def __str__(self):
        return "Jump to label: " + str(self.targetid) + " at most %d times." % self.nrjumps
    def to_configparser(self, cp, sectionname):
        SequenceElement.to_configparser(self, cp, sectionname)
        cp.set(sectionname, 'target', self.targetid)
        cp.set(sectionname, 'nrjumps', self.nrjumps)
    @classmethod
    def from_configparser(cls, cp, sectionname):
        super(SequenceElementLoop, cls).from_configparser(cp, sectionname)
        return cls(cp.get(sectionname, 'target'), cp.getint(sectionname, 'nrjumps'))
    def get_dialog(self, credo, parent=None):
        dia = SequenceElement.get_dialog(self, credo, parent)
        vb = dia.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, True, True, 0)
        
        row = 0
        l = Gtk.Label(label='Label ID:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        dia.id_entry = Gtk.Entry()
        dia.id_entry.set_text(self.targetid)
        tab.attach(dia.id_entry, 1, 2, row, row + 1)
        row += 1
        l = Gtk.Label(label='Nr of jumps:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        dia.nrjumps_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.nrjumps, 0, 10000, 1, 10), digits=0)
        tab.attach(dia.nrjumps_entry, 1, 2, row, row + 1)
        row += 1
       
        return dia
    def update_from_dialog(self, credo, dia):
        self.targetid = dia.id_entry.get_text()
        self.nrjumps = dia.nrjumps_entry.get_value_as_int()


class AddCommandDialog(Gtk.Dialog):
    def __init__(self, title='Add new sequence element', parent=None, flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                 buttons=(Gtk.STOCK_ADD, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        vb = self.get_content_area()
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, False, False, 0)
        l = Gtk.Label('Element type:'); l.set_alignment(0, 0.5)
        hb.pack_start(l, False, False, 0)
        self._elementtype_combo = Gtk.ComboBoxText()
        hb.pack_start(self._elementtype_combo, True, True, 0)
        for sc in SequenceElement.__subclasses__():
            self._elementtype_combo.append_text(sc.__name__.replace('SequenceElement', ''))
        self._elementtype_combo.set_active(0)
        f = Gtk.Frame(label='Documentation')
        vb.pack_start(f, True, True, 0)
        self._doclabel = Gtk.Label()
        self._doclabel.set_alignment(0, 0.5)
        f.add(self._doclabel)

        self._elementtype_combo.connect('changed', self.on_command_changed)
        self.on_command_changed(None)        
        self.show_all()
    def get_command(self):
        name = self._elementtype_combo.get_active_text()
        return [sc for sc in SequenceElement.__subclasses__() if sc.__name__.replace('SequenceElement', '') == name][0]
    def on_command_changed(self, combo):
        cmd = self.get_command()
        self._doclabel.set_label(cmd.__doc__)
        
class SAXSSequence(ToolDialog):
    RESPONSE_SAVE = 1
    RESPONSE_OPEN = 2
    def __init__(self, credo, title='SAXS Sequence'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_SAVE, self.RESPONSE_SAVE, Gtk.STOCK_OPEN, self.RESPONSE_OPEN, Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        self.connect('response', self.on_response)
        self.sequence = Gtk.ListStore(GObject.TYPE_STRING,  # element string
                                      GObject.TYPE_OBJECT,  # element object
                                      )
        vb = self.get_content_area()
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, True, True, 0)
        sw = Gtk.ScrolledWindow()
        hb.pack_start(sw, True, True, 0)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.sequenceview = Gtk.TreeView(self.sequence)
        sw.add(self.sequenceview)
        self.sequenceview.append_column(Gtk.TreeViewColumn('Command', Gtk.CellRendererText(), text=0))
        self.sequenceview.set_headers_visible(True)
        sel = self.sequenceview.get_selection()
        sel.set_mode(Gtk.SelectionMode.SINGLE)
        
        vbb = Gtk.ButtonBox(orientation=Gtk.Orientation.VERTICAL)
        hb.pack_start(vbb, False, False, 0)
        for stock, callback in [(Gtk.STOCK_ADD, lambda button:self.on_add_element()),
                                (Gtk.STOCK_REMOVE, lambda button:self.on_remove_element()),
                                (Gtk.STOCK_EDIT, lambda buton:self.on_edit_element()),
                                (Gtk.STOCK_GOTO_TOP, lambda button:self.on_move_element('top')),
                                (Gtk.STOCK_GO_UP, lambda button:self.on_move_element('up')),
                                (Gtk.STOCK_GO_DOWN, lambda button:self.on_move_element('down')),
                                (Gtk.STOCK_GOTO_BOTTOM, lambda button:self.on_move_element('bottom')),
                                (Gtk.STOCK_CLEAR, lambda button:self.on_clear()),
                                ]:
            b = Gtk.Button(stock=stock)
            b.connect('clicked', callback)
            vbb.pack_start(b, True, True, 0)
            del b
    
    def on_add_element(self):
        dia = AddCommandDialog()
        if dia.run() == Gtk.ResponseType.OK:
            el = dia.get_command()()
            el.edit_with_dialog(self.credo)
            
            model, iter = self.sequenceview.get_selection().get_selected()
            iter = model.insert_after(iter)
            model[iter] = (str(el), el)
            self.sequenceview.get_selection().select_iter(iter)
        dia.destroy()
        del dia
    def on_edit_element(self):
        model, iter = self.sequenceview.get_selection().get_selected()
        if iter is not None:
            model[iter][-1].edit_with_dialog(self.credo)
    def on_remove_element(self):
        model, iter = self.sequenceview.get_selection().get_selected()
        if iter is None: return
        model.remove(iter)
    def on_move_element(self, where):
        model, iter = self.sequenceview.get_selection().get_selected()
        if iter is None: return
        if where == 'top':
            model.move_after(iter, None)
        elif where == 'bottom':
            model.move_before(iter, None)
        elif where == 'up':
            prev = model.iter_previous(iter)
            if prev is not None:
                model.move_before(iter, prev)
        elif where == 'next':
            next = model.iter_next(iter)
            if next is not None:
                model.move_after(iter, next)
        else:
            raise NotImplementedError(where)
    def on_clear(self):
        self.sequence.clear()
    def on_saveorload(self, what):
        if not hasattr(self, '_fcd'):
            self._fcd = Gtk.FileChooserDialog('Save automatic sequence to...', self, Gtk.FileChooserAction.SAVE, (Gtk.STOCK_SAVE, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
            ff = Gtk.FileFilter(); ff.set_name('All files (*)'); ff.add_pattern('*'); self._fcd.add_filter(ff)
            ff = Gtk.FileFilter(); ff.set_name('Automatic sequence files (*.aseq)'); ff.add_pattern('*.aseq'); self._fcd.add_filter(ff)
            self._fcd.set_filter(ff)
            if what == 'save':
                self._fcd.set_current_name('untitled.aseq')
        if what == 'save':
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
            if what == 'save':
                self.save_to(filename)
            elif what == 'load':
                self.load_from(filename)
        self._fcd.hide()
    def save_to(self, filename):
        cp = ConfigParser.ConfigParser()
        cp.add_section('AutoSeq')
        for i, row in enumerate(self.sequence):
            row[-1].to_configparser(cp, 'Element%d' % i)
        try:
            with open(filename, 'w') as f:
                cp.write(f)
        except IOError as ioe:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Could not save program to file ' + filename + '.')
            md.format_secondary_text('Reason: ' + ioe.message)
            md.run()
            md.destroy()
            del md
    def load_from(self, filename):
        cp = ConfigParser.ConfigParser()
        try:
            with open(filename, 'r') as f:
                cp.readfp(f)
            if not cp.has_section('AutoSeq'):
                raise ValueError('Invalid file format: no AutoSeq section present.')
            self.sequence.clear()
            for i in sorted([int(sec.replace('Element', '')) for sec in cp.sections() if sec.startswith('Element')]):
                el = SequenceElement.new_from_configparser(cp, 'Element%d' % i)
                self.sequence.append((str(el), el))
        except (IOError, ValueError) as err:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Could not load program from file ' + filename + '.')
            md.format_secondary_text('Reason: ' + err.message)
            md.run()
            md.destroy()
            del md
    def on_commandended(self, cmd, status):
        if cmd is not None:  # a command ended. If it is None, this is the first command to execute.
            cmd.disconnect(self._cmdconnection)
            if isinstance(cmd, SequenceElementLoop) and status:
                try:
                    self.nextcommand = self.sequence.get_iter([i for i in range(len(self.sequence)) if isinstance(self.sequence[i][-1], SequenceElementLabel) and self.sequence[i][-1].id == cmd.targetid][0])
                except IndexError:
                    md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot jump to nonexistent label: ' + cmd.targetid + '.')
                    md.run()
                    md.destroy()
                    del md
                    self.nextcommand = None
            else:
                self.nextcommand = self.sequence.iter_next(self.nextcommand)
        if self.nextcommand is None:
            # end sequence
            self.get_content_area().set_sensitive(True)
            self.get_action_area().set_sensitive(True)
            self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_EXECUTE)
        else:
            cmd = self.sequence[self.nextcommand][-1]
            self._cmdconnection = cmd.connect('finished', self.on_commandended)
            result = cmd.execute(self.credo)
            
    def on_response(self, dialog, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            self.hide()
        elif respid == Gtk.ResponseType.OK:
            # execute or break execution
            if self.get_widget_for_response(Gtk.ResponseType.OK).get_label() == Gtk.STOCK_EXECUTE:
                # execute
                self.nextcommand = self.sequence.get_iter_first()
                self.get_content_area().set_sensitive(False)
                self.get_action_area().set_sensitive(False)
                self.get_widget_for_response(Gtk.ResponseType.OK).set_sensitive(True)
                self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_STOP)
                self.on_commandended(None, True) 
            else:
                # break
                self.sequence[self.nextcommand][-1].break_operation(self.credo)
        elif respid == self.RESPONSE_SAVE:
            self.on_saveorload('save')
        elif respid == self.RESPONSE_OPEN:
            self.on_saveorload('load') 
        else:
            raise NotImplementedError()
