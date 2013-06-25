import logging
import logging.handlers
import sys
import os
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.handlers.TimedRotatingFileHandler(os.path.expanduser('~/SAXSCtrl.log'), 'D')
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(formatter)
logger.addHandler(handler)

import utils
import hardware
import widgets

__all__ = ['hardware', 'widgets', 'logging', 'utils']

