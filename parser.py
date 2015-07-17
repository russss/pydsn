# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
from decimal import Decimal
import time
import requests
import logging
import dateutil.parser
from lxml import etree


def to_decimal(value):
    if value == '' or value == 'null':
        return None
    return Decimal(value)


class DSNParser(object):

    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.http_session = requests.Session()

    def get_url(self):
        return "http://eyes.nasa.gov/dsn/data/dsn.xml?r=%s" % (int)(time.time() / 5)

    def get_config_url(self):
        return "http://eyes.nasa.gov/dsn/config.xml"

    def fetch_data(self):
        url = self.get_url()
        self.log.debug("Fetching %s" % url)
        response = self.http_session.get(url)
        doc = etree.fromstring(response.content)
        dishes = doc.xpath('/dsn/dish')
        result = {}
        for dish in dishes:
            dish_name, data = self.parse_dish(dish)
            result[dish_name] = data
        return result

    def parse_dish(self, dish):
        data = {
            'azimuth_angle': to_decimal(dish.get('azimuthAngle')),       # Degrees
            'elevation_angle': to_decimal(dish.get('elevationAngle')),   # Degrees
            'wind_speed': to_decimal(dish.get('windSpeed')),             # km/h
            'mspa': dish.get('isMSPA') == 'true',                   # Multiple Spacecraft Per Aperture
            'array': dish.get('isArray') == 'true',                 # Dish is arrayed
            'ddor': dish.get('isDDOR') == 'true',                   # Delta-Differenced One Way Range
            'created': dateutil.parser.parse(dish.get('created')),
            'updated': dateutil.parser.parse(dish.get('updated')),
            'targets': {},
            'up_signal': [],
            'down_signal': []
        }
        for target in dish.findall('target'):
            name, target_data = self.parse_target(target)
            data['targets'][name] = target_data

        for up_signal in dish.findall('upSignal'):
            data['up_signal'].append(self.parse_signal(up_signal))

        for down_signal in dish.findall('downSignal'):
            data['down_signal'].append(self.parse_signal(down_signal))

        if 'DSN' in data['targets']:
            # A target of 'DSN' seems to indicate that the dish is out of service
            data['targets'] = {}
            data['up_signal'] = []
            data['down_signal'] = []
            data['online'] = False
        else:
            data['online'] = True

        return dish.get('name'), data

    def parse_target(self, target):
        data = {
            'id': int(target.get('id')),
            'up_range': Decimal(target.get('uplegRange')),        # Up leg range, meters
            'down_range': Decimal(target.get('downlegRange')),    # Down leg range, meters
            'rtlt': Decimal(target.get('rtlt'))                   # Round-trip light time, in seconds
        }
        return target.get('name'), data

    def parse_signal(self, signal):
        if signal.get('spacecraft') == 'DSN':
            # DSN is a bogus spacecraft
            return None
        data = {
            'type': signal.get('signalType'),                   # "data", "carrier", "ranging", or "none"
            'debug': signal.get('signalTypeDebug'),             # Interesting signal debug info
            'spacecraft': signal.get('spacecraft')
        }

        if signal.get('power') == '':
            data['power'] = None
        else:
            data['power'] = to_decimal(signal.get('power'))    # Power (in dBm for downlink, kW for uplink.)

        if signal.get('frequency') == '' or signal.get('frequency') == 'none':
            data['frequency'] = None
        else:
            data['frequency'] = to_decimal(signal.get('frequency'))   # Frequency (Hz). Always present but may be wrong if type is none

        if signal.get('dataRate') == '':
            data['data_rate'] = None
        else:
            data['data_rate'] = to_decimal(signal.get('dataRate'))    # Data rate, bits per second

        return data

    def fetch_config(self):
        url = self.get_config_url()
        self.log.debug("Fetching config %s" % url)
        response = self.http_session.get(url)
        doc = etree.fromstring(response.content)
        spacecraft = self.fetch_spacecraft(doc.xpath('/config/spacecraftMap/spacecraft'))
        sites = self.fetch_sites(doc.xpath('/config/sites/site'))
        return sites, spacecraft

    def fetch_spacecraft(self, spacecraft):
        data = {}
        for craft in spacecraft:
            data[craft.get('name')] = craft.get('friendlyName')
        return data

    def fetch_sites(self, sites):
        data = {}
        for site in sites:
            dishes = {}
            for dish in site.findall('dish'):
                dishes[dish.get('name')] = {
                    'friendly_name': dish.get('friendlyName'),
                    'type': dish.get('type')
                }
            data[site.get('name')] = {
                'friendly_name': site.get('friendlyName'),
                'dishes': dishes
            }
        return data

if __name__ == '__main__':
    parser = DSNParser()
    from pprint import pprint
    pprint(parser.fetch_data())
