# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
from collections import namedtuple, defaultdict, deque
from datetime import datetime, timedelta
import ConfigParser
import logging
import pickle
import tweepy
from tweepy.error import TweepError
from dsn import DSN

spacecraft_twitter_names = {
    'MSL': 'MarsCuriosity',
    'NHPC': 'NewHorizons2015',
    'ROSE': 'ESA_Rosetta',
    'CAS': 'CassiniSaturn',
    'MOM': 'MarsOrbiter',
    'KEPL': 'NASAKepler'
}

dscc_locations = {
    'mdscc': (40.429167, -4.249167),
    'cdscc': (-35.401389, 148.981667),
    'gdscc': (35.426667, -116.89)
}


def to_GHz(freq):
    if freq is None:
        return None
    return str(round(float(freq) / 10 ** 9, 4))


def format_datarate(rate):
    if rate < 1000:
        return "%sb/s" % (int(rate))
    elif rate < 500000:
        return "%skb/s" % (round(rate / 1000, 1))
    else:
        return "%sMb/s" % (round(rate / 1000000, 1))

# This state represents the per-spacecraft data which needs to change
# in order to (possibly) generate a tweet
State = namedtuple("State", ['antenna',   # Antenna identifier
                             'status',    # Status (none, carrier, data)
                             'data',
                             'timestamp'
                             ])


def state_changed(a, b):
    # Avoid announcing antenna changes at the moment, as
    # it causes flapping if two antennas are receiving one craft simultaneously.
    return not (a.status == b.status)


def combine_state(signals):
    """ Given a number of signals from a spacecraft, find the most notable. """
    if len(signals) == 1:
        data = signals[0]
        status = data['type']
    else:
        status = 'none'
        data = signals[0]  # Pick one signal in case we don't find a more interesting one
        for signal in signals:
            if signal['type'] == 'carrier' and status == 'none':
                status = 'carrier'
                data = signal
            elif signal['type'] == 'data' and status in ('carrier', 'none'):
                status = 'data'
                data = signal
    return State(data['antenna'], status, data, datetime.now())


class TweetDSN(object):
    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.config = ConfigParser.ConfigParser()
        self.config.read('dsntweet.conf')
        auth = tweepy.OAuthHandler(self.config.get('twitter', 'api_key'),
                                   self.config.get('twitter', 'api_secret'))
        auth.set_access_token(self.config.get('twitter', 'access_key'),
                              self.config.get('twitter', 'access_secret'))
        self.twitter = tweepy.API(auth)
        self.pending_updates = {}
        self.state = {}
        self.last_updates = {}
        self.spacecraft_blacklist = set(['TEST', 'GRAY', 'GBRA', 'DSN', 'VLBI', 'RSTS'])

    def data_callback(self, _old, new):
        signals = defaultdict(list)
        for antenna, status in new.iteritems():
            # Spacecraft can have more than one downlink signal, but antennas can also be
            # receiving from more than one spacecraft
            for signal in status['down_signal']:
                signal['antenna'] = antenna
                signals[signal['spacecraft']].append(signal)

        new_state = {}
        for spacecraft, sc_signals in signals.iteritems():
            new_state[spacecraft] = combine_state(sc_signals)

        self.update_state(new_state)
        self.process_updates()

    def update_state(self, new_state):
        for spacecraft, state in new_state.iteritems():
            if spacecraft in self.spacecraft_blacklist:
                continue
            if spacecraft not in self.state:
                # New spacecraft, save its state for future reference:
                self.log.info("New spacecraft seen: %s" % spacecraft)
                self.state[spacecraft] = state
            elif state_changed(self.state[spacecraft], state):
                self.queue_update(spacecraft, state)

    def queue_update(self, spacecraft, state):
        # Do we already have an update queued for this spacecraft?
        if spacecraft in self.pending_updates:
            update = self.pending_updates[spacecraft]
            # Has the state changed since the last update was queued?
            if not state_changed(update['state'], state):
                self.log.debug("Queueing new update for %s: %s", spacecraft, state)
                update['state'] = state
            else:
                # Update has changed, bump the timestamp
                self.log.debug("Postponing update for %s: %s", spacecraft, state)
                update = {'state': state, 'timestamp': datetime.now()}
        else:
            self.pending_updates[spacecraft] = {'state': state, 'timestamp': datetime.now()}

    def process_updates(self):
        new_updates = {}
        tweets = deferred = 0
        for spacecraft, update in self.pending_updates.iteritems():
            if update['timestamp'] < datetime.now() - timedelta(seconds=63):
                tweets += 1
                self.tweet(spacecraft, update['state'])
                self.state[spacecraft] = update['state']
            else:
                deferred += 1
                new_updates[spacecraft] = update
        self.pending_updates = new_updates
        if tweets > 0 or deferred > 0:
            self.log.info("%s state updates processed, %s updates deferred", tweets, deferred)

    def tweet(self, spacecraft, state):
        if not self.should_tweet(spacecraft, state):
            self.log.info("Not tweeting about %s being in state %s", spacecraft, state)
            return

        if spacecraft in spacecraft_twitter_names:
            sc_name = '@' + spacecraft_twitter_names[spacecraft]
        else:
            sc_name = self.dsn.spacecraft.get(spacecraft.lower(), spacecraft)

        antenna = self.antenna_info(state.antenna)
        if antenna['site'] not in dscc_locations:
            self.log.warn("Antenna site %s not found in dscc_locations", antenna['site'])
            return
        lat, lon = dscc_locations[antenna['site']]
        old_state = self.state[spacecraft]
        message = None
        if state.status == 'carrier' and old_state.status == 'none':
            message = "%s carrier lock on %s\nFrequency: %sGHz\n" % \
                      (antenna['friendly_name'], sc_name,
                       to_GHz(state.data['frequency']))
            # Ignore obviously wrong Rx power numbers - sometimes we see a lock before
            # Rx power settles down.
            if state.data['power'] > -200:
                message += "Signal strength: %sdBm\n" % (int(state.data['power']))
            message += state.data['debug']
        if state.status == 'data' and old_state.status in ('none', 'carrier'):
            message = "%s receiving data from %s at %s.\n%s" % \
                      (antenna['friendly_name'], sc_name, format_datarate(state.data['data_rate']),
                       state.data['debug'])
        if message is not None:
            if spacecraft not in self.last_updates:
                self.last_updates[spacecraft] = deque(maxlen=25)
            self.last_updates[spacecraft].append((datetime.now(), state))
            try:
                self.twitter.update_status(status=message, lat=lat, long=lon)
            except TweepError:
                self.log.exception("Tweet error")
            print(message)

    def should_tweet(self, spacecraft, state):
        """ Last check to decide if we should tweet this update. Don't tweet about the same
            (spacecraft, antenna, status) more than once every n hours."""
        if spacecraft not in self.last_updates:
            return True
        for update in self.last_updates[spacecraft]:
            timestamp, previous_state = update
            if (previous_state.status == state.status and
                    previous_state.antenna == state.antenna and
                    timestamp > datetime.now() - timedelta(hours=6)):
                return False
        return True

    def antenna_info(self, antenna):
        for site, site_info in self.dsn.sites.iteritems():
            for ant, antenna_info in site_info['dishes'].iteritems():
                if antenna == ant:
                    return {"site_friendly_name": site_info['friendly_name'],
                            "site": site,
                            "friendly_name": antenna_info['friendly_name']}

    def run(self):
        logging.basicConfig(level=logging.INFO)
        self.dsn = DSN()
        self.dsn.data_callback = self.data_callback

        try:
            with open("./state.pickle", "r") as f:
                self.state, self.last_updates = pickle.load(f)
        except IOError:
            self.log.exception("Failure loading state file, resetting")

        self.log.info("Running")
        try:
            self.dsn.run()
        finally:
            self.log.info("Saving state...")
            with open("./state.pickle", "w") as f:
                pickle.dump((self.state, self.last_updates), f, pickle.HIGHEST_PROTOCOL)
            self.log.info("Shut down.")

TweetDSN().run()
