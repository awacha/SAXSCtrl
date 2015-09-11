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
import pkg_resources
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

from . import utils
from . import hardware
from . import widgets

__all__ = ['hardware', 'widgets', 'utils']

itheme = Gtk.IconTheme.get_default()
itheme.append_search_path(
    pkg_resources.resource_filename('saxsctrl', 'resource/icons/scalable'))


class LogException(Exception):
    pass


def start_saxsctrl():
    try:
        os.mkdir('log')
    except OSError:
        pass
    isonline = 'ONLINE' in [x.upper() for x in sys.argv]
    if isonline:
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
    pb = itheme.load_icon('saxsctrl_icon', 256, 0)
    Gtk.Window.set_default_icon(pb)

    if isonline and os.path.isfile('/run/user/%d/SAXSCtrl.pid' % os.geteuid()):
        md = Gtk.MessageDialog(parent=None, flags=None, type=Gtk.MessageType.ERROR,
                               buttons=Gtk.ButtonsType.CLOSE, message_format='Another instance of this program is running')
        md.run()
    elif isonline:
        with open('/run/user/%d/SAXSCtrl.pid' % os.geteuid(), 'w') as f:
            f.write(str(os.getpid()))

        root = widgets.root.RootWindow()
        root.show_all()
        Gtk.main()
        root.destroy()
        gc.collect()
    logger.info('Ending main program.')
