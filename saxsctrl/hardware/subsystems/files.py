import os
import re
import logging
from .subsystem import SubSystem, SubSystemError
import sastool
import numpy as np
import h5py
import datetime
import dateutil.tz
import pkg_resources
from ..instruments import InstrumentError
import scipy.constants
import time
import traceback

from gi.repository import GObject
from gi.repository import Gio

__all__ = ['SubSystemFiles']

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DEFAULT_FILEPREFIXES = ['crd', 'tst', 'scn', 'tra']

HC = scipy.constants.codata.value(
    'Planck constant in eV s') * scipy.constants.codata.value('speed of light in vacuum') * 1e9  # nm*eV


class SubSystemFiles(SubSystem):
    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_FIRST, None, ()),  # emitted whenever properties filebegin or ndigits, or the list of watched folders change
                    # emitted whenever the next fsn from the current format
                    # changes.
                    'new-nextfsn': (GObject.SignalFlags.RUN_FIRST, None, (int, str)),
                    # emitted whenever the first fsn from the current format
                    # changes.
                    'new-firstfsn': (GObject.SignalFlags.RUN_FIRST, None, (int, str)),
                    'notify': 'override',
                    }
    filebegin = GObject.property(
        type=str, default='crd', blurb='First part of exposure names')
    ndigits = GObject.property(
        type=int, default=5, minimum=1, blurb='Number of digits in exposure names')
    rootpath = ''
    scanfilename = GObject.property(
        type=str, default='credoscan.spec', blurb='Scan file')

    def __init__(self, credo, offline=True, createdirsifnotpresent=False):
        self.rootpath = os.getcwd()
        SubSystem.__init__(self, credo, offline)
        self.monitors = []
        self.create_subdirs(createdirsifnotpresent)
        self._setup(self.rootpath)
        self.scanfile = None
        self.scanfilename = 'credoscan.spec'
        self._lastevents = []

    def __del__(self):
        self._disconnect_monitors()

    def do_notify(self, prop):
        if prop.name in ['filebegin', 'ndigits']:
            self.emit('changed')
        if prop.name in ['scanfilename']:
            if not os.path.isabs(self.scanfilename):
                self.scanfilename = os.path.join(
                    self.scanpath, self.scanfilename)
            else:
                self.reload_scanfile()

    def reload_scanfile(self):
        if isinstance(self.scanfile, sastool.classes.SASScanStore):
            self.scanfile.finalize()
            del self.scanfile
        logger.debug('Reloading scan file from ' + self.scanfilename + '')
        self.scanfile = sastool.classes.SASScanStore(
            self.scanfilename, 'CREDO spec file', [])
        logger.debug('Scan file reloaded: ' + str(self.scanfile))
        return self.scanfile

    def _disconnect_monitors(self):
        for monitor, connection in self.monitors:
            monitor.cancel()
            monitor.disconnect(connection)
        self.monitors = []

    def _setup(self, rootpath):
        logger.debug('Running SubSystemFiles._setup()')
        self._disconnect_monitors()
        if self.rootpath != rootpath:
            logger.debug('SubSystemFiles._setup(): setting rootpath to %s (was: %s)' % (
                rootpath, self.rootpath))
            self.rootpath = rootpath
        self.monitors = []
        for folder in self._watchpath():
            dirmonitor = Gio.file_new_for_path(folder).monitor_directory(
                Gio.FileMonitorFlags.NONE, None)
            self.monitors.append(
                (dirmonitor, dirmonitor.connect('changed', self._on_monitor_event)))
            logger.debug(
                'SubSystemFiles._setup(): Added directory monitor for path %s' % folder)
        self._nextfsn_cache = {}
        self._firstfsn_cache = {}
        for f in self._search_formats():
            self.get_next_fsn(self.get_format_re(f, self.ndigits, False))
            self.get_first_fsn(self.get_format_re(f, self.ndigits, False))

    def _watchpath(self):
        return [self._get_subpath(subdir) for subdir in ['images', 'param', 'eval2d', 'eval1d']]

    def _search_formats(self):
        regex = re.compile('(?P<begin>[a-zA-Z0-9]+)_(?P<fsn>\d+)')
        formats = set(DEFAULT_FILEPREFIXES)
        for pth in self.exposureloadpath:
            formats.update({m.groupdict()['begin'] for m in [
                           regex.match(f) for f in os.listdir(pth)] if (m is not None)})
        return list(sorted(set(formats)))

    def _known_regexes(self):
        return set(self._nextfsn_cache.keys()).union(set(self._firstfsn_cache.keys()))

    def formats(self):
        return sorted([p.pattern.split('_')[0] for p in self._known_regexes()])

    def _on_monitor_event(self, monitor, filename, otherfilename, event):
        if otherfilename is not None:
            logger.debug('SubSystemFiles._on_monitor_event() starting: filename: ' +
                         filename.get_path() + ', otherfilename: ' +
                         otherfilename.get_path() + ', event: ' + str(event))
        else:
            logger.debug('SubSystemFiles._on_monitor_event() starting: filename: ' +
                         filename.get_path() + ', otherfilename: None, event: ' +
                         str(event))

        if (event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED)):
            basename = filename.get_basename()
            if basename:
                for regex in self._known_regexes():
                    m = regex.match(basename)
                    if m is not None:
                        newfsn = int(m.group(1))
                        if regex in self._nextfsn_cache:
                            if newfsn >= self._nextfsn_cache[regex]:
                                self._nextfsn_cache[
                                    regex] = int(m.group(1)) + 1
                                self.emit(
                                    'new-nextfsn', self._nextfsn_cache[regex], regex.pattern)
                            else:
                                logger.debug(
                                    'Not updating nextfsn: %d <= %d' %
                                    (newfsn + 1, self._nextfsn_cache[regex]))
                        if regex in self._firstfsn_cache:
                            if (self._firstfsn_cache[regex] is None) or (newfsn < self._firstfsn_cache[regex]):
                                self._firstfsn_cache[regex] = int(m.group(1))
                                self.emit(
                                    'new-firstfsn', self._firstfsn_cache[regex], regex.pattern)
                            else:
                                logger.debug(
                                    'Not updating firstfsn: %d >= %d' % (newfsn, self._firstfsn_cache[regex]))
        else:
            logger.debug(
                'SubSystemFiles._on_monitor_event(): nothing to be done.')
        self._lastevents.append(event)

    def do_new_nextfsn(self, nextfsn, repattern):
        logger.debug(
            'SubSystemFiles: new nextfsn: %d for pattern %s' % (nextfsn, repattern))

    def do_new_firstfsn(self, firstfsn, repattern):
        logger.debug(
            'SubSystemFiles: new firstfsn: %d for pattern %s' % (firstfsn, repattern))

    def get_first_fsn(self, regex=None):
        if regex is None:
            regex = self.get_fileformat_re()
        currentpattern = (regex.pattern == self.get_fileformat_re().pattern)
        if regex in self._firstfsn_cache:
            return self._firstfsn_cache[regex]
        logger.debug(
            'SubSystemFiles: finding lowest fsn for files matching pattern %s' % regex.pattern)
        minfsns = []
        for pth in self.exposureloadpath:
            fsns = [int(m.group(1)) for m in [regex.match(f)
                                              for f in os.listdir(pth)] if m is not None]
            if fsns:
                minfsns.append(min(fsns))
        if minfsns:
            self._firstfsn_cache[regex] = min(minfsns)
        else:
            self._firstfsn_cache[regex] = None
        if currentpattern and (self._firstfsn_cache[regex] is not None):
            self.emit(
                'new-firstfsn', self._firstfsn_cache[regex], regex.pattern)
        return self._firstfsn_cache[regex]

    def get_next_fsn(self, regex=None):
        if regex is None:
            regex = self.get_fileformat_re()
        currentpattern = (regex.pattern == self.get_fileformat_re().pattern)
        if regex in self._nextfsn_cache:
            return self._nextfsn_cache[regex]
        logger.debug(
            'SubSystemFiles: finding highest fsn for files matching pattern %s' % regex.pattern)
        maxfsns = [0]
        for pth in self.exposureloadpath:
            fsns = [int(m.group(1)) for m in [regex.match(f)
                                              for f in os.listdir(pth)] if m is not None]
            if fsns:
                maxfsns.append(max(fsns))
        self._nextfsn_cache[regex] = max(maxfsns) + 1
        if currentpattern:
            self.emit('new-nextfsn', self._nextfsn_cache[regex], regex.pattern)
        return self._nextfsn_cache[regex]

    def increment_next_fsn(self, regex=None):
        if regex is None:
            regex = self.get_fileformat_re()
        self._nextfsn_cache[regex] = self.get_next_fsn(regex) + 1
        if (regex.pattern == self.get_fileformat_re().pattern):
            self.emit('new-nextfsn', self._nextfsn_cache[regex], regex.pattern)
        return self._nextfsn_cache[regex]

    def _get_subpath(self, subdir):
        pth = os.path.join(os.path.expanduser(self.rootpath), subdir)
        while os.path.islink(pth):
            pth = os.readlink(pth)
        if not os.path.isdir(pth):
            if not os.path.exists(pth):
                os.mkdir(pth)  # an OSError is raised if no permission.
            else:
                raise OSError('%s exists and is not a directory!' % pth)
        return pth

    @property
    def configpath(self):
        return self._get_subpath('config')

    @property
    def exposureloadpath(self):
        ret = []
        for p in ['eval2d', 'eval1d', 'param_override', 'param', 'images', 'nexus']:
            try:
                ret.append(self._get_subpath(p))
            except OSError:
                logger.warning(
                    'Subpath %s cannot be found, not including it to exposureloadpath!' % p)
        ret.extend(sastool.misc.find_subdirs(self._get_subpath('mask'), None))
        return ret

    @property
    def rawloadpath(self):
        ret = []
        for p in ['param_override', 'param', 'images', 'nexus']:
            try:
                ret.append(self._get_subpath(p))
            except OSError:
                logger.warning(
                    'Subpath %s cannot be found, not including it to exposureloadpath!' % p)
        ret.extend(sastool.misc.find_subdirs(self._get_subpath('mask'), None))
        return ret

    @property
    def reducedloadpath(self):
        ret = []
        for p in ['eval2d', 'eval1d']:
            try:
                ret.append(self._get_subpath(p))
            except OSError:
                logger.warning(
                    'Subpath %s cannot be found, not including it to exposureloadpath!' % p)
        ret.extend(sastool.misc.find_subdirs(self._get_subpath('mask'), None))
        return ret

    @property
    def moviepath(self):
        return self._get_subpath('movie')

    @property
    def parampath(self):
        return self._get_subpath('param')

    @property
    def param_overridepath(self):
        return self._get_subpath('param_override')

    @property
    def maskpath(self):
        return self._get_subpath('mask')

    @property
    def scanpath(self):
        return self._get_subpath('scan')

    @property
    def eval2dpath(self):
        return self._get_subpath('eval2d')

    @property
    def eval1dpath(self):
        return self._get_subpath('eval1d')

    @property
    def imagespath(self):
        return self._get_subpath('images')

    @property
    def nexuspath(self):
        return self._get_subpath('nexus')

    def get_fileformat(self, filebegin=None, ndigits=None):
        if filebegin is None:
            filebegin = self.filebegin
        if ndigits is None:
            ndigits = self.ndigits
        return filebegin + '_' + '%%0%dd' % ndigits

    def get_fileformat_re(self, strict=False):
        return self.get_format_re(self.filebegin, self.ndigits, strict)

    def get_headerformat(self, filebegin=None, ndigits=None):
        return self.get_fileformat(filebegin, ndigits) + '.param'

    def get_nexusformat(self, filebegin=None, ndigits=None):
        return self.get_fileformat(filebegin, ndigits) + '.nx5'

    def get_nexusformat_re(self, strict=False):
        return re.compile(self.get_fileformat_re().pattern + '\.nx5', strict)

    def get_exposureformat(self, filebegin=None, ndigits=None):
        return self.get_fileformat(filebegin, ndigits) + '.cbf'

    def get_headerformat_re(self, strict=False):
        return re.compile(self.get_fileformat_re().pattern + '\.param', strict)

    def get_exposureformat_re(self, strict=False):
        return re.compile(self.get_fileformat_re().pattern + '\.cbf', strict)

    def get_eval2dformat(self, filebegin='crd', ndigits=5):
        return self.get_fileformat(filebegin, ndigits) + '.npz'

    def get_evalheaderformat(self, filebegin='crd', ndigits=5):
        return self.get_fileformat(filebegin, ndigits) + '.param'

    def get_format_re(self, filebegin, ndigits, strict=False):
        if strict:
            return re.compile(filebegin + '_' + '(?P<fsn>\d{%d})' % ndigits)
        else:
            return re.compile(filebegin + '_' + '(?P<fsn>\d+)')

    def writeheader(self, header, raw=True, override=False, headerformat=None):
        if headerformat is None:
            headerformat = self.get_headerformat()
        if raw and override:
            path = self.param_overridepath
        elif raw:
            path = self.parampath
        else:
            path = self.eval2dpath
        header.write(os.path.join(path, headerformat % header['FSN']))

    def writereduced(self, exposure):
        exposure.write(
            os.path.join(self.eval2dpath, self.get_eval2dformat() % exposure['FSN']))
        exposure.header.write(
            os.path.join(self.eval2dpath, self.get_evalheaderformat() % exposure['FSN']))

    def writeradial(self, exposure, pixels_per_qbin=None):
        if pixels_per_qbin is None:
            rad = exposure.radial_average()
        else:
            qrange = exposure.get_qrange()
            pixrange = exposure.get_pixrange()
            Npix = (pixrange.max() - pixrange.min())
            Nq = int(Npix / float(pixels_per_qbin))
            rad = exposure.radial_average(
                np.linspace(qrange.min(), qrange.max(), Nq))
        rad.save(os.path.join(self.eval1dpath, 'crd_%d.txt' % exposure['FSN']))

    def create_subdirs(self, do_create=False):
        for subdir in ['config', 'eval1d', 'eval2d', 'mask', 'movie', 'param', 'param_override', 'png', 'processing', 'scan', 'sequences', 'user', 'log', 'nexus']:
            if os.path.exists(subdir) and os.path.isdir(subdir):
                continue  # nothing to do
            elif os.path.islink(subdir):
                if os.path.exists(subdir) and os.path.isdir(os.path.realpath(subdir)):
                    # valid symlink points to a directory
                    continue
                else:
                    # invalid symlink or points to a non-directory
                    raise SubSystemError(
                        'Subfolder %s is not valid (broken symlink or symlink to a non-directory).' % subdir)
            else:
                # subdir does not exist: we must create it
                if do_create:
                    logger.info('Creating subdirectory ' + subdir)
                    os.mkdir(subdir)
                else:
                    raise SubSystemError(
                        'Cannot create subdirectory, please run program with the "createdirs" command-line option!')

    def create_nexus_template(self, fsn, filebegin=None, ndigits=None, nscan=None):
        if filebegin is None:
            filebegin = self.filebegin
        if ndigits is None:
            ndigits = self.ndigits
        return self._create_nexus_template_file(os.path.join(self.nexuspath, self.get_nexusformat(filebegin, ndigits) % fsn), fsn, nscan)

    def _create_nexus_template_file(self, filename, fsn=None, nscan=None):
        """Creates a NeXus file, just before an exposure. All subsystems are
        considered set-up and ready for the start.

        Inputs:
            filename: string
                the file name to write.
            fsn: integer 
                the file sequence number, if applicable. Either the FSN of an
                exposure or the scan number, see `nscan`.
            nscan: None or integer
                If None, a NeXus file for a single exposure is saved. If an integer,
                this is the number of expected scan points. The NeXus file will
                have the scheme of a scan file. `fsn` will be in this case the scan
                number.
        """
        t0 = time.time()
        with h5py.File(filename, 'w') as f:
            f.attrs['NX_class'] = 'NXroot'
            f.attrs['creator'] = 'SAXSCtrl@CREDO'
            f.attrs['file_name'] = filename
            f.attrs['file_time'] = datetime.datetime.now(
                dateutil.tz.tzlocal()).isoformat()
            f.attrs['HDF5_version'] = h5py.version.hdf5_version
            f.attrs['default'] = 'entry'
            f.attrs['NeXus_version'] = '4.4.0'
            entry = f.create_group('entry')
            entry.attrs['NX_class'] = 'NXentry'
            entry.attrs['default'] = 'data'
            entry['title'] = os.path.splitext(os.path.split(filename)[-1])
            entry['entry_identifier'] = os.path.splitext(
                os.path.split(filename)[-1])[0]
            entry['experiment_identifier'] = self.credo().projectid
            entry['experiment_description'] = self.credo().projectname
            if nscan is None:
                entry['definition'] = 'NXsas'
                entry['definition'].attrs['version'] = '1.0b'
                entry['definition'].attrs[
                    'URL'] = 'https://github.com/nexusformat/definitions/blob/master/applications/NXsas.nxdl.xml'
                entry['collection_time'] = self.credo().subsystems[
                    'Exposure'].exptime
                entry['collection_time'].attrs['units'] = 's'
            else:
                entry['definition'] = 'CREDOscan'
                entry['collection_time'] = self.credo().subsystems[
                    'Exposure'].exptime * nscan
            entry['run_cycle'] = str(datetime.date.today().year)
            entry['program_name'] = 'SAXSCtrl'
            entry['program_name'].attrs[
                'version'] = pkg_resources.get_distribution('saxsctrl').version
            entry['revision'] = '0'
            operator = entry.create_group('operator')
            operator.attrs['NX_class'] = 'NXuser'
            operator['name'] = self.credo().username
            operator['role'] = 'local_contact'

            proposer = entry.create_group('proposer')
            proposer.attrs['NX_class'] = 'NXuser'
            proposer['name'] = self.credo().proposername
            proposer['role'] = 'proposer'

            sam = self.credo().subsystems['Samples'].get()
            if sam is not None:
                samplefrom = entry.create_group('sample_from')
                samplefrom.attrs['NX_class'] = 'NXuser'
                samplefrom['name'] = sam.preparedby
                samplefrom['role'] = 'sample_preparator'

                sample = entry.create_group('sample')
                sample.attrs['NX_class'] = 'NXsample'
                sample['name'] = sam.title
                sample['type'] = sam.category
                sample['situation'] = sam.situation
                sample['description'] = sam.description
                sample['preparation_date'] = sam.preparetime.isoformat()
                sample['thickness'] = float(sam.thickness)
                sample['thickness'].attrs['units'] = 'cm'
                try:
                    sample['thickness_error'] = sam.thickness.err
                    sample['thickness_error'].attrs['units'] = 'cm'
                except AttributeError:
                    pass
                sample['short_title'] = sample['name']
                sample['prepared_by'] = samplefrom
                sample['distance'] = float(sam.distminus)
                sample['distance'].attrs['units'] = 'mm'
                try:
                    sample['distance_error'] = sam.distminus.err
                    sample['distance_error'].attrs['units'] = 'mm'
                except AttributeError:
                    pass
                sample.create_group('transmission')
                sample['transmission'].attrs['NX_class'] = 'NXdata'
                sample['transmission']['data'] = float(sam.transmission)
                try:
                    sample['transmission']['errors'] = sam.transmission.err
                    sample['transmission']['data'].attrs[
                        'uncertainties'] = 'errors'
                except AttributeError:
                    pass
                try:
                    haakephoenix = self.credo().subsystems['Equipments'].get(
                        'haakephoenix')
                    if haakephoenix.connected():
                        sample['temperature'] = haakephoenix.temperature
                        sample['temperature'].attrs['units'] = 'degC'
                except InstrumentError as ie:
                    logger.warn(
                        'Cannot contact Haake Phoenix circulator while saving NeXus file: ', traceback.format_exc())
            monitor = entry.create_group('monitor')
            monitor.attrs['NX_class'] = 'NXmonitor'
            monitor['mode'] = 'timer'
            monitor['preset'] = self.credo().subsystems[
                'Exposure'].exptime
            monitor['preset'].attrs['units'] = 's'
            monitor['nominal'] = self.credo().subsystems[
                'Exposure'].exptime
            monitor['nominal'].attrs['units'] = 's'
            monitor['type'] = 'timer'
            monitor['count_time'] = self.credo().subsystems['Exposure'].exptime
            monitor['count_time'].attrs['units'] = 's'
            instrument = entry.create_group('instrument')
            instrument.attrs['NX_class'] = 'NXinstrument'
            instrument['name'] = 'Creative Research Equipment for DiffractiOn'
            instrument['name'].attrs['short_name'] = 'CREDO'
            instrument['URL'] = 'http://credo.ttk.mta.hu'
            l0 = self.credo().subsystems['Collimation'].l0
            l1 = self.credo().subsystems['Collimation'].l1
            l2 = self.credo().subsystems['Collimation'].l2
            ls = self.credo().subsystems['Collimation'].ls
            lbs = self.credo().subsystems['Collimation'].lbs
            dbs = self.credo().subsystems['Collimation'].dbs
            sd = self.credo().dist
            beamstop = instrument.create_group('beam_stop')
            beamstop.attrs['NX_class'] = 'NXbeam_stop'
            beamstop['description'] = 'circular'
            beamstop['size'] = dbs
            beamstop['size'].attrs['units'] = 'mm'
            beamstop['distance_to_detector'] = lbs
            beamstop['distance_to_detector'].attrs['units'] = 'mm'
            coll = instrument.create_group('collimator')
            coll.attrs['NX_class'] = 'NXcollimator'
            for idx, description, dist in [(1, 'Entrance', -(l1 + l2 + ls)),
                                           (2, 'Beam defining', (-(l2 + ls))),
                                           (3, 'Guard', (-ls))]:
                ph = coll.create_group('aperture_%d' % idx)
                ph.attrs['NX_class'] = 'NXaperture'
                ph['material'] = 'Pt-Ir'
                ph['description'] = description + ' pinhole'
                geo = ph.create_group('geometry')
                geo.attrs['NX_class'] = 'NXgeometry'
                geo['component_index'] = idx - 4
                shape = geo.create_group('shape')
                shape.attrs['NX_class'] = 'NXshape'
                shape['shape'] = 'nxcylinder'
                shape.create_dataset('size', data=np.array(
                    [[getattr(self.credo().subsystems['Collimation'], 'aperture%d' % idx) * 1e-3, 0.2, 0, 0, 1.]]))
                shape['size'].attrs['units'] = 'mm'
                trans = geo.create_group('translation')
                trans.attrs['NX_class'] = 'NXtranslation'

                trans.create_dataset(
                    'distances', data=np.array([[0, 0, dist]]))
                trans['distances'].attrs['units'] = 'mm'

            motors = instrument.create_group('motors')
            motors.attrs['NX_class'] = 'NXcollection'
            for m in self.credo().subsystems['Motors']:
                motor = self.credo().subsystems['Motors'].get(m)
                mot = motors.create_group(motor.name)
                mot.attrs['NX_class'] = 'NXpositioner'
                mot['name'] = motor.name
                mot['description'] = motor.alias
                mot['value'] = motor.get_parameter(
                    'Current_position', raw=False)
                mot['value'].attrs['units'] = 'mm'
                mot['raw_value'] = motor.get_parameter(
                    'Current_position', raw=True)
                mot['raw_value'].attrs['units'] = ''
                mot['soft_limit_min'] = motor.get_parameter(
                    'soft_left', raw=False)
                mot['soft_limit_min'].attrs['units'] = 'mm'
                mot['soft_limit_max'] = motor.get_parameter(
                    'soft_right', raw=False)
                mot['soft_limit_max'].attrs['units'] = 'mm'
                if motor == self.credo().subsystems['Samples'].motor_samplex:
                    sample['positioner_x'] = mot
                    sample['x_translation'] = mot['value']
                elif motor == self.credo().subsystems['Samples'].motor_sampley:
                    sample['positioner_y'] = mot
                    sample['y_translation'] = mot['value']
                elif motor == self.credo().subsystems['Collimation'].motor_beamstopx:
                    beamstop['positioner_x'] = mot
                    beamstop['x'] = mot['value']
                elif motor == self.credo().subsystems['Collimation'].motor_beamstopy:
                    beamstop['positioner_y'] = mot
                    beamstop['y'] = mot['value']
                    beamstop['status'] = ['out', 'in'][
                        (mot['value'] < self.credo().subsystems['Collimation'].beamstop_in_ymax) and
                        (mot['value'] > self.credo().subsystems['Collimation'].beamstop_in_min)]
                elif motor == self.credo().subsystems['Collimation'].motor_ph1x:
                    coll['aperture_1']['positioner_x'] = mot
                    coll['aperture_1']['x'] = mot['value']
                elif motor == self.credo().subsystems['Collimation'].motor_ph1y:
                    coll['aperture_1']['positioner_y'] = mot
                    coll['aperture_1']['y'] = mot['value']
                elif motor == self.credo().subsystems['Collimation'].motor_ph2x:
                    coll['aperture_2']['positioner_x'] = mot
                    coll['aperture_2']['x'] = mot['value']
                elif motor == self.credo().subsystems['Collimation'].motor_ph2y:
                    coll['aperture_2']['positioner_y'] = mot
                    coll['aperture_2']['y'] = mot['value']
                elif motor == self.credo().subsystems['Collimation'].motor_ph3x:
                    coll['aperture_3']['positioner_x'] = mot
                    coll['aperture_3']['x'] = mot['value']
                elif motor == self.credo().subsystems['Collimation'].motor_ph3y:
                    coll['aperture_3']['positioner_y'] = mot
                    coll['aperture_3']['y'] = mot['value']
            monochromator = instrument.create_group('monochromator')
            monochromator.attrs['NX_class'] = 'NXmonochromator'
            monochromator['wavelength'] = self.credo().wavelength
            monochromator['wavelength'].attrs['units'] = 'nm'
            monochromator['wavelength_error'] = self.credo().wavelength *\
                self.credo().wavelength_spread
            monochromator['wavelength_error'].attrs['units'] = 'nm'
            monochromator['energy'] = HC / self.credo().wavelength
            monochromator['energy'].attrs['units'] = 'eV'
            monochromator['energy_error'] = monochromator[
                'energy'].value * self.credo().wavelength_spread
            monochromator['energy_error'].attrs['units'] = 'eV'
            source = instrument.create_group('source')
            source.attrs['NX_class'] = 'NXsource'
            source['distance'] = -ls - l2 - l1 - l0
            source['name'] = 'Xenocs GeniX3D Cu ULD'
            source['name'].attrs['short_name'] = 'GeniX'
            source['type'] = 'Fixed Tube X-ray'
            source['probe'] = 'x-ray'
            try:
                genix = self.credo().subsystems['Equipments'].get('genix')
                ht = genix.ht
                curr = genix.current
                source['power'] = ht * curr
                source['power'].attrs['units'] = 'W'
                source['energy'] = ht * 1000
                source['energy'].attrs['units'] = 'eV'
                source['current'] = curr * 1e-3
                source['current'].attrs['units'] = 'A'
            except InstrumentError:
                logger.warn(
                    'Could not contact GeniX for saving NeXus file: ' + traceback.format_exc())
            source['target_material'] = 'Cu'
            sensors = instrument.create_group('sensors')
            sensors.attrs['NX_class'] = 'NXcollection'
            try:
                vacgauge = self.credo().subsystems['Equipments'].get(
                    'vacgauge')
                p = vacgauge.pressure
                vacuum = sensors.create_group('vacuum')
                vacuum.attrs['NX_class'] = 'NXsensor'
                vacuum['value'] = p
                vacuum['value'].attrs['units'] = 'mbar'
                vacuum['model'] = vacgauge.get_version()
                vacuum['name'] = 'Pirani Vacuum Gauge'
                vacuum['short_name'] = 'vacgauge'
                vacuum['attached_to'] = 'flight path'
                vacuum['measurement'] = 'pressure'
                vacuum['type'] = 'Pirani'
                vacuum['run_control'] = False
            except InstrumentError:
                logger.warn(
                    'Cannot contact vacuum gauge on saving NeXus file: ' + traceback.format_exc())
            detector = instrument.create_group('detector')
            detector.attrs['NX_class'] = 'NXdetector'
            detector['distance'] = sd
            detector['distance'].attrs['units'] = 'mm'
            detector['polar_angle'] = 0
            detector['polar_angle'].attrs['units'] = 'rad'
            detector['azimuthal_angle'] = 0
            detector['azimuthal_angle'].attrs['units'] = 'rad'
            detector['local_name'] = 'pilatus300k'
            detector['x_pixel_size'] = 0.172
            detector['x_pixel_size'].attrs['units'] = 'mm'
            detector['y_pixel_size'] = 0.172
            detector['y_pixel_size'].attrs['units'] = 'mm'
            detector['type'] = 'CMOS'
            detector['layout'] = 'area'
            detector['count_time'] = self.credo().subsystems[
                'Exposure'].exptime
            detector['count_time'].attrs['units'] = 's'
            if fsn is not None:
                detector['sequence_number'] = fsn
            detector['beam_center_x'] = self.credo().beamposy * \
                detector['x_pixel_size'].value
            detector['beam_center_x'].attrs['units'] = 'mm'
            detector['beam_center_y'] = self.credo().beamposx * \
                detector['y_pixel_size'].value
            detector['beam_center_y'].attrs['units'] = 'mm'
            detector['acquisition_mode'] = 'summed'
            detector['angular_calibration_applied'] = False
            detector['flatfield_applied'] = True
            detector.create_dataset('pixel_mask', data=(
                self.credo().subsystems['Exposure'].get_mask().mask == 0) << 6)
            detector['pixel_mask'].attrs[
                'file_name'] = self.credo().subsystems['Exposure'].default_mask
            detector['countrate_correction_applied'] = True
            detector['bit_depth_readout'] = 20
            detector['detector_readout_time'] = 2.3
            detector['detector_readout_time'].attrs['units'] = 'ms'
            detector['sensor_material'] = 'Si'
            detector['sensor_thickness'] = 450e-3
            detector['sensor_thickness'].attrs['units'] = 'mm'
            try:
                pilatus = self.credo().subsystems['Equipments'].get('pilatus')
                detector[
                    'description'] = 'Dectris Pilatus-300k SN: %s' % pilatus.camerasn
                detector['comparator_voltage'] = pilatus.vcmp
                detector['comparator_voltage'].attrs['units'] = 'V'
                detector['dead_time'] = pilatus.tau * 1e9
                detector['dead_time'].attrs['units'] = 'ns'
                detector['gain_setting'] = pilatus.gain
                detector['threshold_energy'] = pilatus.threshold
                detector['threshold_energy'].attrs['units'] = 'eV'
                detector['saturation_value'] = pilatus.cutoff
                for i, attached_to in zip(list(range(3)), ['power board', 'base plate', 'sensor']):
                    hum = sensors.create_group('detector_humidity%d' % i)
                    hum.attrs['NX_class'] = 'NXsensor'
                    hum['value'] = getattr(pilatus, 'humidity%d' % i)
                    hum['value'].attrs['units'] = '%'
                    hum['model'] = 'Pilatus-300k'
                    hum['name'] = 'Humidity sensor, channel #%d' % (12 + i)
                    hum['short_name'] = 'Humidity #%d' % i
                    hum['attached_to'] = 'Detector power board'
                    hum['measurement'] = 'humidity'
                    hum['type'] = 'combined temperature and humidity sensor'
                    hum['run_control'] = False
                    temp = sensors.create_group('detector_temperature%d' % i)
                    temp.attrs['NX_class'] = 'NXsensor'
                    temp['value'] = getattr(pilatus, 'temperature%d' % i)
                    temp['value'].attrs['units'] = 'deg_C'
                    temp['model'] = 'Pilatus-300k'
                    temp['name'] = 'Temperature sensor, channel #%d' % (12 + i)
                    temp['short_name'] = 'Temperature #%d' % i
                    temp['attached_to'] = 'Detector ' + attached_to
                    temp['measurement'] = 'temperature'
                    temp['type'] = 'combined temperature and humidity sensor'
                    temp['run_control'] = False

            except InstrumentError:
                logger.warn(
                    'Cannot contact pilatus for data retrieval on saving NeXus file: ' + traceback.format_exc())
            data = entry.create_group('data')
            data.attrs['NX_class'] = 'NXdata'

            monitor['start_time'] = datetime.datetime.now(
                dateutil.tz.tzlocal()).isoformat()
            entry['start_time'] = monitor['start_time']
        logger.debug('Created NeXus template file %s in %.2f seconds' %
                     (filename, time.time() - t0))
        return
