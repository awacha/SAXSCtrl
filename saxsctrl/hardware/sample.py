class SAXSSample(object):
    def __init__(self, title, position=0, thickness=1, transmission=1, temperature=25):
        self.title = title
        self.position = position
        self.thickness = thickness
        self.transmission = transmission
        self.temperature = temperature
    def __repr__(self):
        return 'SAXSSample(%s, %.2f, %.4f, %.4f, %.2f)' % (self.title, self.position, self.thickness, self.transmission, self.temperature)
    def __str__(self):
        return 'SAXSSample(%s, %.2f, %.4f, %.4f, %.2f)' % (self.title, self.position, self.thickness, self.transmission, self.temperature)
    def __unicode__(self):
        return u'SAXSSample(%s, %.2f, %.4f, %.4f, %.2f)' % (self.title, self.position, self.thickness, self.transmission, self.temperature)
