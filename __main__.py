import logging
import logging.handlers
import saxsctrl.widgets
import os
import subprocess
import gc
import multiprocessing
import sys

logger = logging.getLogger('saxsctrl')

from gi.repository import Gtk

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
            # raise LogException('Error transmitting message: ' + results[0])
        del p
        # print "Emitted message: ", message
        # print "Command line:", cmdline
        # print "Results: ", results
        
# handler = ELOG_Handler()
# handler.setLevel(logging.WARNING)
# logger.addHandler(handler)
# formatter = logging.Formatter('%(message)s\n\nTime: %(asctime)s\nFacility: %(name)s\nLevel: %(levelname)s\nSource :%(pathname)s (line %(lineno)d)')
# handler.setFormatter(formatter)    

logger.info('SAXSCtrl started')


def send_to_elog():
    category = 'Software'
    subject = 'testsubject'
    status = 'DEBUG'
    cmdline = "elog -h localhost -a Type=System -a Category=\"%s\" -a Author=\"CREDO System\" -u system metsysoderc -l CREDO -p 8080 -a Subject=\"%s\" -a Status=\"%s\"" % (category, subject, status)
    p = subprocess.Popen(cmdline, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.communicate('test message')
    del p


if __name__ == '__main__':
    root = saxsctrl.widgets.root.RootWindow()
    root.show_all()
    try:
        __IPYTHON__
    except NameError:
        def func(*args, **kwargs):
            return Gtk.main_quit()
        root.connect('delete-event', func)
        Gtk.main()
        root.destroy()
        gc.collect()
    logger.info('Ending main program.')
    
    
