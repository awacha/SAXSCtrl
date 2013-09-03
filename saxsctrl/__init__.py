import matplotlib
matplotlib.use('Gtk3Agg')
import logging
import logging.handlers
import sys
import os
from gi.repository import Gtk
from gi.repository import GObject
import subprocess
import warnings
import gc

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
handler.setLevel(logging.WARNING)

import utils
import hardware
import widgets

__all__ = ['hardware', 'widgets', 'utils']

class LogException(Exception):
    pass

class ELOG_Handler(logging.Handler):
    def __init__(self, hostname='bionano.mta-kk', port='8080', username='system', password='metsysoderc', logbook='CREDO_SYS', type_='System', authorname='CREDO System'):
        logging.Handler.__init__(self)
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.type_ = type_
        self.authorname = authorname
        self.logbook = logbook
    def emit(self, record):
        message = self.format(record)
        if 'genix' in record.name.lower():
            category = 'GeniX'
        elif 'pilatus' in record.name.lower():
            category = 'Pilatus300k'
        elif 'root' in record.name.lower():
            category = 'Software'
        else:
            category = 'Other'
        
        pars = {'hostname':self.hostname, 'port':self.port, 'username':self.username, 'password':self.password,
                'type':self.type_, 'authorname':self.authorname, 'category':category,
                'subject':record.msg, 'status':record.levelname.upper(), 'logbook':self.logbook}
        cmdline = "elog -h %(hostname)s -a Type=\"%(type)s\" -a Category=\"%(category)s\" -a Author=\"%(authorname)s\" -u %(username)s %(password)s -l %(logbook)s -p %(port)s -a Subject=\"%(subject)s\" -a Status=\"%(status)s\"" % pars 
        p = subprocess.Popen(cmdline, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        results = p.communicate(message)
        if not results[0].startswith('Message successfully'):
            print "Error transmitting message: " + results[0]
        del p

def start_saxsctrl():
    try:
        os.mkdir('log')
    except OSError:
        pass
    if 'ONLINE' in [x.upper() for x in sys.argv]:
        handler = logging.handlers.TimedRotatingFileHandler(os.path.expanduser('log/SAXSCtrl.log'), 'D')
    else:
        handler = logging.handlers.TimedRotatingFileHandler(os.path.expanduser('log/SAXSCtrl_OFFLINE.log'), 'D')
    formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # logging.captureWarnings(True)
    warnings.filterwarnings('always')
    
    GObject.threads_init()
            
    # handler = ELOG_Handler()
    # handler.setLevel(logging.WARNING)
    # logger.addHandler(handler)
    # formatter = logging.Formatter('%(message)s\n\nTime: %(asctime)s\nFacility: %(name)s\nLevel: %(levelname)s\nSource :%(pathname)s (line %(lineno)d)')
    # handler.setFormatter(formatter)    
    
    logger.info('SAXSCtrl started')
    root = widgets.root.RootWindow()
    root.show_all()
    Gtk.main()
    root.destroy()
    gc.collect()
    logger.info('Ending main program.')
    
