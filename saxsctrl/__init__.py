import matplotlib
matplotlib.use('Gtk3Agg')
import logging
import logging.handlers
import sys
import os
from gi.repository import Gtk
from gi.repository import GObject
# from gi.repository import Notify
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

# Notify.init('SAXSCtrl')
import sastool
sastool.libconfig.LENGTH_UNIT = 'nm'

import utils
import hardware
import widgets

__all__ = ['hardware', 'widgets', 'utils']


class LogException(Exception):
    pass


def start_saxsctrl():
    try:
        os.mkdir('log')
    except OSError:
        pass
    if 'ONLINE' in [x.upper() for x in sys.argv]:
        handler = logging.handlers.TimedRotatingFileHandler(
            os.path.expanduser('log/SAXSCtrl.log'), 'D')
    else:
        handler = logging.handlers.TimedRotatingFileHandler(
            os.path.expanduser('log/SAXSCtrl_OFFLINE.log'), 'D')
    formatter = logging.Formatter(
        '%(asctime)s:%(name)s:%(levelname)s:%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # logging.captureWarnings(True)
    warnings.filterwarnings('always')

    logger.info('SAXSCtrl started')
    root = widgets.root.RootWindow()
    root.show_all()
    Gtk.main()
    root.destroy()
    gc.collect()
    logger.info('Ending main program.')
