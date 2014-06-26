# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
from time import sleep
import logging
from decimal import Decimal
from datetime import datetime
from datetime import timedelta
from parser import DSNParser


class DSN(object):
    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.parser = DSNParser()
        self.last_config_update = None
        self.data = None

    def update(self):
        if self.last_config_update is None or \
           self.last_config_update < datetime.now() - timedelta(minutes=10):
            self.sites, self.spacecraft = self.parser.fetch_config()

        new_data = self.parser.fetch_data()
        if self.data is not None:
            self.compare_data(self.data, new_data)

        self.data = new_data

    def compare_data(self, old, new):
        pass

    def run(self):
        while True:
            self.update()
            sleep(5)

if __name__ == '__main__':
    dsn = DSN()
    dsn.run()
