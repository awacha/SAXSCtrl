import sastool
import numpy as np

class Scan(object):
    def __init__(self, filename):
        self._metadata = {'Owner':'Anonymous', 'Project':'No project'}
        self._colnames = []
        self._data = None
        with open(filename, 'rt') as f:
            readingmode = 'firstline'
            for l in f:
                if readingmode == 'firstline':
                    self._metadata['type'], self._metadata['FSN'] = l[1:].strip().split('#')
                    self._metadata['FSN'] = int(self._metadata['FSN'])
                    readingmode = 'header'
                elif readingmode == 'header' and ':' in l:
                    left, right = l[1:].strip().split(':', 1)
                    right = sastool.misc.parse_number(right.strip(), use_dateutilparser=True)
                    self._metadata[left.strip()] = right
                elif l.startswith('# Scan data follows.'):
                    readingmode = 'columns'
                elif readingmode == 'columns':
                    self._colnames = l[1:].strip().split('\t')
                    readingmode = 'data'
                elif readingmode == 'data':
                    self._data = np.loadtxt(f)
    def get_dataset(self, colname):
        if isinstance(colname, basestring):
            colname = self._colnames.index(colname)
        return self._data[:, colname]
    def get_metadata(self, name):
        return self._metadata[name]
    def __getitem__(self, key):
        return self.get_metadata(key)
    def __setitem__(self, key, value):
        return self._metadata.__setitem__(key, value)
    def keys(self):
        return self._metadata.keys()
    def __len__(self):
        try:
            return self._data.shape[0]
        except AttributeError:
            return 0
    def get_colnames(self):
        return self._colnames
