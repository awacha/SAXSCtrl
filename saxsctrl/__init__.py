import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


import hardware
import widgets

__all__ = ['hardware', 'widgets', 'logging']

