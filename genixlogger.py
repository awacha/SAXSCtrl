import genix
import logging
import time

host = 'genix.saxs'

logger = logging.getLogger(__name__)
formatter = logging.Formatter('%(asctime)s|%(created)d|%(message)s')
handler = logging.FileHandler('genixlog.txt', mode='a')
logger.addHandler(handler)
handler.setFormatter(formatter)
logger.setLevel(logging.DEBUG)
genixcontroller = genix.GenixConnection(host)

while True:
    time.sleep(1)
    ht = genixcontroller.get_ht()
    curr = genixcontroller.get_current()
    coils = genixcontroller.get_status_bits()
    logger.info('HT=%.2f kV, Curr=%.3f mA, Bits=%s' % (ht, curr, ''.join([str(c) for c in coils])))
    
