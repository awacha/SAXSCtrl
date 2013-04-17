import datetime
import dateutil.parser
import ConfigParser
from sastool.misc.errorvalue import ErrorValue

class SAXSSample(object):
    title = None
    positiony = 0.0
    positionx = 0.0
    thickness = 1.0
    transmission = 1.0
    temperature = 25.0
    preparedby = 'Anonymous'
    preparetime = None
    distminus = 0.0
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
    def __init__(self, title, positiony=0.0, positionx=0.0, thickness=1.0, transmission=1.0, temperature=25.0, preparedby='Anonymous', preparetime=None, distminus=0.0):
        if isinstance(title, SAXSSample):
            self.title = title.title
            self.positionx = title.positionx
            self.positiony = title.positiony
            self.thickness = title.thickness
            self.transmission = title.transmission
            self.temperature = title.temperature
            self.preparedby = title.preparedby
            self.preparetime = title.preparetime
            self.distminus = title.distminus
        else:
            self.title = title
            self.positionx = positionx
            self.positiony = positiony
            self.thickness = thickness
            self.transmission = transmission
            self.temperature = temperature
            self.preparedby = preparedby
            if preparetime is None:
                preparetime = datetime.datetime.now()
            self.preparetime = preparetime
            self.distminus = distminus
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
        cp.set(sectionname, 'Temperature', float(self.temperature))
        if isinstance(self.temperature, ErrorValue):
            cp.set(sectionname, 'TemperatureError', self.temperature.err)
        cp.set(sectionname, 'Preparedby', self.preparedby)
        cp.set(sectionname, 'Preparetime', str(self.preparetime))
        cp.set(sectionname, 'Distminus', float(self.distminus))
        if isinstance(self.distminus, ErrorValue):
            cp.set(sectionname, 'DistminusError', self.distminus.err)
    def read_from_ConfigParser(self, cp, sectionname):
        for name, attr in [('Title', 'title'), ('Preparedby', 'preparedby') ]:
            if cp.has_option(sectionname, name):
                self.__setattr__(attr, cp.get(sectionname, name))
        for name, attr in [('Position', 'positiony'), ('PositionY', 'positiony'), ('PositionX', 'positionx'), ('Thickness', 'thickness'), ('Transmission', 'transmission'),
                           ('Temperature', 'temperature'), ('Distminus', 'distminus')]:
            if cp.has_option(sectionname, name):
                self.__setattr__(attr, cp.getfloat(sectionname, name))
                if cp.has_option(sectionname, name + 'Error'):
                    self.__setattr__(name, ErrorValue(self.__getattribute__(attr), cp.getfloat(sectionname, name + 'Error')))
        if cp.has_option(sectionname, 'Preparetime'):
            self.preparetime = dateutil.parser.parse(cp.get(sectionname, 'Preparetime'))
    def __repr__(self):
        return 'SAXSSample(%s, (%.3f, %.03f), %.4f, %.4f, %.2f)' % (self.title, self.positionx, self.positiony, self.thickness, self.transmission, self.temperature)
    def __str__(self):
        return 'SAXSSample(%s, (%.3f, %.03f), %.4f, %.4f, %.2f)' % (self.title, self.positionx, self.positiony, self.thickness, self.transmission, self.temperature)
    def __unicode__(self):
        return u'SAXSSample(%s, (%.3f, %.03f) %.4f, %.4f, %.2f)' % (self.title, self.positionx, self.positiony, self.thickness, self.transmission, self.temperature)
    def __eq__(self, other):
        if not isinstance(other, SAXSSample):
            return False
        for attr in ['title', 'thickness', 'temperature', 'preparedby', 'preparetime']:
            if self.__getattribute__(attr) != other.__getattribute__(attr):
                return False
        return True
    def __ne__(self, other):
        return not self.__eq__(other)
    def __lt__(self, other):
        return self.title < other.title
    def __le__(self, other):
        return self.title <= other.title
    def __gt__(self, other):
        return not self.__le__(other)
    def __ge__(self, other):
        return not self.__lt__(other)
    def get_header(self):
        hed = {'Title':self.title, 'Preparedby':self.preparedby, 'Preparetime':self.preparetime}
        for attr, key in [('thickness', 'Thickness'), ('transmission', 'Transm'), ('positiony', 'PosSample'), ('positionx', 'PosSampleX'), ('temperature', 'Temperature'), ('distminus', 'DistMinus')]:
            hed[key] = float(self.__getattribute__(attr)) 
            if isinstance(self.__getattribute__(attr), ErrorValue):
                hed[key + 'Error'] = self.__getattribute__(attr).err
        return hed
        
