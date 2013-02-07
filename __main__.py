import logging
import logging.handlers
import saxsctrl.widgets
import os
logger = logging.root
logger.setLevel(logging.DEBUG)
handler = logging.handlers.TimedRotatingFileHandler(os.path.expanduser('~/SAXSCtrl.log'), 'D')
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.info('SAXSCtrl started')


import gtk


if __name__ == '__main__':
    root = saxsctrl.widgets.root.RootWindow()
    root.show_all()
    try:
        __IPYTHON__
    except NameError:
        def func(*args, **kwargs):
            return gtk.main_quit()
        root.connect('delete-event', func)
        gtk.main()
    logger.info('Ending main program.')
