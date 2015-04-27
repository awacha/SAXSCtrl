import datetime
import dateutil.parser
import ConfigParser
from sastool.misc.errorvalue import ErrorValue


VALID_CATEGORIES = ['calibration sample',
                    'normalization sample', 'sample', 'sample+can', 'can', 'none']

VALID_SITUATIONS = ['air', 'vacuum', 'sealed can']


class SAXSSample(object):
    title = None
    positiony = 0.0
    positionx = 0.0
    thickness = 1.0
    transmission = 1.0
    preparedby = 'Anonymous'
    preparetime = None
    distminus = 0.0
    description = ''
    category = None  # a string. Can be any element of VALID_CATEGORIES
    situation = None  # a string. Can be any element of VALID_SITUATIONS

    @classmethod
    def new_from_cfg(cls, *filenames):
        cp = ConfigParser.ConfigParser()
        cp.read(filenames)
        lis = []
        for section in cp.sections():
            obj = cls('')
            obj.read_from_ConfigParser(cp, section)
            lis.append(obj)
        del cp
        return lis

    def __init__(self, title, positiony=0.0, positionx=0.0, thickness=1.0,
                 transmission=1.0, preparedby='Anonymous', preparetime=None,
                 distminus=0.0, description='', category='sample', situation='vacuum'):
        if isinstance(title, SAXSSample):
            self.title = title.title
            self.positionx = title.positionx
            self.positiony = title.positiony
            self.thickness = title.thickness
            self.transmission = title.transmission
            self.preparedby = title.preparedby
            self.preparetime = title.preparetime
            self.distminus = title.distminus
            self.description = title.description
            self.category = title.category
            self.situation = title.situation
        else:
            self.title = title
            self.positionx = positionx
            self.positiony = positiony
            self.thickness = thickness
            self.transmission = transmission
            self.preparedby = preparedby
            self.category = category
            if preparetime is None:
                preparetime = datetime.datetime.now()
            self.preparetime = preparetime
            self.distminus = distminus
            self.description = description
            self.situation = situation

    def save_to_ConfigParser(self, cp, sectionname):
        if not cp.has_section(sectionname):
            cp.add_section(sectionname)
        cp.set(sectionname, 'Title', self.title)
        cp.set(sectionname, 'PositionX', float(self.positionx))
        if isinstance(self.positionx, ErrorValue):
            cp.set(sectionname, 'PositionXError', self.positionx.err)
        cp.set(sectionname, 'PositionY', float(self.positiony))
        if isinstance(self.positiony, ErrorValue):
            cp.set(sectionname, 'PositionYError', self.positiony.err)
        cp.set(sectionname, 'Thickness', float(self.thickness))
        if isinstance(self.thickness, ErrorValue):
            cp.set(sectionname, 'ThicknessError', self.thickness.err)
        cp.set(sectionname, 'Transmission', float(self.transmission))
        if isinstance(self.transmission, ErrorValue):
            cp.set(sectionname, 'TransmissionError', self.transmission.err)
        cp.set(sectionname, 'Preparedby', self.preparedby)
        cp.set(sectionname, 'Preparetime', str(self.preparetime))
        cp.set(sectionname, 'Distminus', float(self.distminus))
        if isinstance(self.distminus, ErrorValue):
            cp.set(sectionname, 'DistminusError', self.distminus.err)
        cp.set(sectionname, 'Description', str(self.description))
        cp.set(sectionname, 'Category', str(self.category))
        cp.set(sectionname, 'Situation', str(self.situation))

    def read_from_ConfigParser(self, cp, sectionname):
        for name, attr in [('Title', 'title'), ('Preparedby', 'preparedby'), ('Description', 'description'), ('Category', 'category'), ('Situation', 'situation')]:
            if cp.has_option(sectionname, name):
                self.__setattr__(attr, cp.get(sectionname, name))
        for name, attr in [('Position', 'positiony'),
                           ('PositionY', 'positiony'),
                           ('PositionX', 'positionx'),
                           ('Thickness', 'thickness'),
                           ('Transmission', 'transmission'),
                           ('Distminus', 'distminus'),
                           ]:
            if cp.has_option(sectionname, name):
                self.__setattr__(attr, cp.getfloat(sectionname, name))
                if cp.has_option(sectionname, name + 'Error'):
                    self.__setattr__(
                        attr, ErrorValue(self.__getattribute__(attr),
                                         cp.getfloat(sectionname, name + 'Error')))
        if cp.has_option(sectionname, 'Preparetime'):
            self.preparetime = dateutil.parser.parse(
                cp.get(sectionname, 'Preparetime'))

    def __repr__(self):
        return 'SAXSSample(%s, (%.3f, %.3f), %.4f, %.4f)' % (self.title,
                                                             self.positionx, self.positiony, self.thickness, self.transmission)

    def __str__(self):
        return '%s, (%.3f, %.3f), %.4f cm, transm: %.4f' % (self.title,
                                                            self.positionx, self.positiony, self.thickness, self.transmission)

    def __unicode__(self):
        return u'%s, (%.3f, %.3f) %.4f cm, transm: %.4f' % (self.title,
                                                            self.positionx, self.positiony, self.thickness, self.transmission)

    def __eq__(self, other):
        if isinstance(other, SAXSSample):
            for attr in ['title', 'thickness', 'preparedby', 'preparetime']:
                if self.__getattribute__(attr) != other.__getattribute__(attr):
                    return False
            return True
        elif isinstance(other, basestring):
            if self.title == other:
                return True
        else:
            return NotImplemented

    def __ne__(self, other):
        return not (self == other)

    def __lt__(self, other):
        return self.title < other.title

    def __le__(self, other):
        return self.title <= other.title

    def __gt__(self, other):
        return not self.__le__(other)

    def __ge__(self, other):
        return not self.__lt__(other)

    def get_header(self):
        hed = {'Title': self.title, 'Preparedby':
               self.preparedby, 'Preparetime': self.preparetime,
               'SampleDescription': self.description}
        for attr, key in [('thickness', 'Thickness'),
                          ('transmission', 'Transm'),
                          ('positiony', 'PosSample'),
                          ('positionx', 'PosSampleX'),
                          ('distminus', 'DistMinus'),
                          ]:
            hed[key] = float(self.__getattribute__(attr))
            if isinstance(self.__getattribute__(attr), ErrorValue):
                hed[key + 'Error'] = self.__getattribute__(attr).err
        return hed
