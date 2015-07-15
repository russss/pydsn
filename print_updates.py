# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
import logging
from dsn import DSN


def to_GHz(freq):
    if freq is None:
        return None
    return str(round(float(freq) / 10 ** 9, 8))


def update_callback(antenna, old, new):
    if len(new['down_signal']) == 0:
        return
    for i in range(0, len(new['down_signal'])):
        signal = new['down_signal'][i]

        if len(old['down_signal']) > i - 1:
            old_signal = old['down_signal'][i]
            if (to_GHz(signal['frequency']) == to_GHz(old_signal['frequency']) and
                    signal['debug'] == old_signal['debug'] and
                    signal['spacecraft'] == old_signal['spacecraft']):
                # No change, don't print anything
                return

        print("%s tracking %s\tstatus: %s\tfrequency: %sGHz" %
              (antenna, signal['spacecraft'], signal['debug'], to_GHz(signal['frequency'])))


logging.basicConfig()
dsn = DSN()
dsn.update_callback = update_callback
dsn.run()
