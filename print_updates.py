import logging
from dsn import DSN


def to_GHz(freq):
    if freq is None:
        return None
    return str(round(float(freq) / 10 ** 9, 4))


def update_callback(antenna, old, new):
    if len(new['down_signal']) == 0:
        return
    for i in range(0, len(new['down_signal'])):
        signal = new['down_signal'][i]

        if len(old['down_signal']) > i:
            old_signal = old['down_signal'][i]
            if (to_GHz(signal['frequency']) == to_GHz(old_signal['frequency']) and
                    signal['debug'] == old_signal['debug'] and
                    signal['spacecraft'] == old_signal['spacecraft']):
                # No change, don't print anything
                return

        print("%s channel %s\ttracking %s\tstatus: %s\tinfo: %s\tfrequency: %sGHz" %
              (antenna, i, signal['spacecraft'], signal['type'],
               signal['debug'], to_GHz(signal['frequency'])))


logging.basicConfig(level=logging.DEBUG)
dsn = DSN()
dsn.update_callback = update_callback
dsn.run()
