import datetime

class SAXSSample(object):
    title = None
    position = 0
    thickness = 1
    transmission = 1
    temperature = 25
    preparedby = 'Anonymous'
    preparetime = None
    distminus = 0
    def __init__(self, title, position=0, thickness=1, transmission=1, temperature=25, preparedby='Anonymous', preparetime=None, distminus=0):
        if isinstance(title, SAXSSample):
            self.title = title.title
            self.position = title.position
            self.thickness = title.thickness
            self.transmission = title.transmission
            self.temperature = title.temperature
            self.preparedby = title.preparedby
            self.preparetime = title.preparetime
            self.distminus = title.distminus
        else:
            self.title = title
            self.position = position
            self.thickness = thickness
            self.transmission = transmission
            self.temperature = temperature
            self.preparedby = preparedby
            if preparetime is None:
                preparetime = datetime.datetime.now()
            self.preparetime = preparetime
            self.distminus = distminus
    def __repr__(self):
        return 'SAXSSample(%s, %.2f, %.4f, %.4f, %.2f)' % (self.title, self.position, self.thickness, self.transmission, self.temperature)
    def __str__(self):
        return 'SAXSSample(%s, %.2f, %.4f, %.4f, %.2f)' % (self.title, self.position, self.thickness, self.transmission, self.temperature)
    def __unicode__(self):
        return u'SAXSSample(%s, %.2f, %.4f, %.4f, %.2f)' % (self.title, self.position, self.thickness, self.transmission, self.temperature)
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
