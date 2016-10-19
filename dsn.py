# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
from time import sleep
import logging
from datetime import datetime
from datetime import timedelta
from requests.exceptions import ConnectionError
from lxml.etree import LxmlError
from parser import DSNParser


class DSN(object):
    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.parser = DSNParser()
        self.last_config_update = None
        self.status_update_interval = 5  # Seconds
        self.config_update_interval = 600  # Seconds
        self.data = None
        self.update_callback = None  # Called per-antenna if the status has changed
        self.data_callback = None    # Called for every new data update

    def update(self):
        try:
            if self.last_config_update is None or \
               self.last_config_update < datetime.now() - timedelta(minutes=self.config_update_interval):
                self.sites, self.spacecraft = self.parser.fetch_config()
            new_data = self.parser.fetch_data()
        except ConnectionError as e:
            self.log.warn("Unable to fetch data from DSN: %s" % e)
            return
        except LxmlError as e:
            self.log.warn("Unable to parse data: %s", e)
            return

        if self.data is not None:
            self.compare_data(self.data, new_data)
            if self.data_callback:
                self.data_callback(self.data, new_data)

        self.data = new_data

    def compare_data(self, old, new):
        if not self.update_callback:
            return

        for antenna, new_status in new.iteritems():
            if antenna not in old:
                # Antenna has gone away (oh no)
                continue
            old_status = old[antenna]
            # The "updated" flag doesn't get flipped except for especially significant status
            # changes, but we care about them all
            updated = new_status['updated'] > old_status['updated']
            for signal in ('down_signal', 'up_signal'):
                if (len(new_status[signal]) > 0 and len(old_status[signal]) == 0) or \
                   (len(new_status[signal]) > 0 and
                        new_status[signal][0]['debug'] != old_status[signal][0]['debug']):
                    updated = True
            if updated:
                self.update_callback(antenna, old_status, new_status)

    def run(self):
        while True:
            self.update()
            sleep(self.status_update_interval)
