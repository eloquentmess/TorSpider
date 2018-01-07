#!/usr/bin/env python3
# -*- coding: utf-8 -*-

''' TorSpider – A script to explore the darkweb.
    -------------------by Christopher Steffen---

    TorSpider will explore the darkweb to discover as many onion sites as
    possible, storing them all in a database along with whatever additional
    information can be found. It will also store data regarding which sites
    connected to which other sites, allowing for some relational mapping.

    The database generated by TorSpider will be accessible via a secondary
    script which will create a web interface for exploring the saved data.
'''

import os
import sys
import requests
import sqlite3 as sql
from datetime import datetime
from html.parser import HTMLParser


'''---GLOBAL VARIABLES---'''


# Let's use the default Tor Browser Bundle UA:
agent = 'Mozilla/5.0 (Windows NT 6.1; rv:52.0) Gecko/20100101 Firefox/52.0'

# Just to prevent some SSL errors.
requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += \
                                              ':ECDHE-ECDSA-AES128-GCM-SHA256'


'''---CLASS DEFINITIONS---'''


class parse_links(HTMLParser):
    # Parse given HTML for all a.href links.
    def __init__(self):
        HTMLParser.__init__(self)
        self.output_list = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.output_list.append(dict(attrs).get('href'))


class parse_title(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.match = False
        self.title = ''

    def handle_starttag(self, tag, attributes):
        self.match = True if tag == 'title' else False

    def handle_data(self, data):
        if self.match:
            self.title = data
            self.match = False


'''---FUNCTION DEFINITIONS---'''


def crawl():
    ''' This function is the meat of the program, doing all the heavy lifting
        of crawling the website and scraping up all the juicy data therein.
    '''
    pass


def db_cmd(command):
    # This function executes commands in the database.
    output = None
    connection = sql.connect('SpiderWeb.db')
    cursor = connection.cursor()
    try:
        command = command.strip()
        cursor.execute(command)
        if(command.upper().startswith("SELECT")):
            output = cursor.fetchall()
    except sql.Error as e:
        log("SQL Error: {}".format(e))
    connection.commit()
    connection.close()
    if(output is not None):
        try:
            (output, ) = output[0]
        except Exception as e:
            log("SQL Error: {}".format(e))
            output = None
    return output


def extract_exact(items, scan_list):
    # Return all items from items list that match items in scan_list.
    return [item for item in items
            if any(scan == item for scan in scan_list)]


def extract_fuzzy(items, scan_list):
    # Return all items from items list that match items in scan_list.
    return [item for item in items
            if any(scan in item for scan in scan_list)]


def get_domain(link):
    # Given a link, extract the domain.
    split = link.split('/')
    return prune_exact(split, ['http:', 'https:', ''])[0]


def get_links(data):
    # Given HTML input, return a list of all unique links.
    parse = parse_links()
    parse.feed(data)
    return unique([link for link in parse.output_list if link is not None])


def get_onion_domains(domains):
    # Get a list of onion-specific domains from a list of various domains.
    return unique([domain for domain in domains if '.onion' in domain])


def get_timestamp():
    # Get a time stamp that fits Sqlite3's DATETIME format.
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def get_title(data):
    # Given HTML input, return the title of the page.
    parse = parse_title()
    parse.feed(data)
    return parse.title.strip()


def get_tor_session():
    # Create a session that's routed through Tor.
    session = requests.session()
    session.headers.update({'User-Agent': agent})
    session.proxies = {
            'http':  'socks5h://127.0.0.1:9050',
            'https': 'socks5h://127.0.0.1:9050'
        }
    return session


def get_unique_domains(links):
    # Given HTML input, return a list of all unique domains.
    return unique([get_domain(link) for link in links])


def log(line):
    print('{} - {}'.format(get_timestamp(), line))


def prune_exact(items, scan_list):
    # Return all items from items list that match no items in scan_list.
    return [item for item in items
            if not any(scan == item for scan in scan_list)]


def prune_fuzzy(items, scan_list):
    # Return all items from items list that match no items in scan_list.
    return [item for item in items
            if not any(scan in item for scan in scan_list)]


def unique(items):
    # Return the same list without duplicates)
    return list(set(items))


'''---MAIN---'''


if __name__ == '__main__':
    log('TorSpider initializing...')

    # Create a Tor session and check if it's working.
    log("Establishing Tor connection...")
    session = get_tor_session()
    try:
        local_ip = requests.get('http://api.ipify.org/').text
        tor_ip = session.get('http://api.ipify.org/').text
        if(local_ip == tor_ip):
            log("Tor connection failed: IPs match.")
            sys.exit(0)
        else:
            log("Tor connection established.")
    except Exception as e:
        log("Tor connection failed: {}".format(e))
        sys.exit(0)

    if(not os.path.exists('SpiderWeb.db')):
        # The database doesn't yet exist. Let's establish a new database.
        log("Initializing new database...")

        # First, we'll set up the database structure.

        ''' Onions: Information about each individual onion domain.
                - id:       The numerical ID of that domain.
                - domain:   The domain itself (i.e. 'google.com').
                - online:   Whether the domain was online as of the last scan.
                - date:     The date of the last scan.
                - info:     Any additional information known about the domain.
        '''
        db_cmd("CREATE TABLE IF NOT EXISTS `onions` ( \
                        `id` INTEGER PRIMARY KEY, \
                        `domain` TEXT, \
                        `online` INTEGER DEFAULT '1', \
                        `date` DATETIME DEFAULT '1986-02-02 00:00:01', \
                        `info` TEXT DEFAULT 'none');")

        ''' Pages: Information about each link discovered.
                - id:       The numerical ID of that page.
                - title:    The page's title.
                - domain:   The numerical ID of the page's parent domain.
                - url:      The URL for the page.
                - hash:     The page's sha1 hash, for detecting changes.
                - date:     The date of the last scan.
        '''
        db_cmd("CREATE TABLE IF NOT EXISTS `pages` ( \
                        `id` INTEGER PRIMARY KEY, \
                        `title` TEXT DEFAULT 'none', \
                        `domain` INTEGER, \
                        `url` TEXT, \
                        `hash` TEXT DEFAULT 'none', \
                        `date` DATETIME DEFAULT '1986-02-02 00:00:01');")

        ''' Links: Information about which domains are connected to each other.
                - domain:   The numerical ID of the origin domain.
                - link:     The numerical ID of the target domain.
        '''
        db_cmd('CREATE TABLE IF NOT EXISTS `links` ( \
                        `domain` INTEGER, \
                        `link` INTEGER);')

        # Next, we'll populate the database with some default values. These
        # pages are darknet indexes, so they should be a good starting point.

        # The Uncensored Hidden Wiki
        # http://zqktlwi4fecvo6ri.onion/wiki/Main_Page
        db_cmd("INSERT INTO `onions` (`domain`) VALUES ( \
                    'zqktlwi4fecvo6ri.onion' \
                );")
        db_cmd("INSERT INTO `pages` (`domain`, `url`) VALUES ( \
                    '1', \
                    '/wiki/Main_Page' \
               );")

        # OnionDir
        # https://auutwvpt2zktxwng.onion/
        db_cmd("INSERT INTO `onions` (`domain`) VALUES ( \
                    'auutwvpt2zktxwng.onion' \
                );")
        db_cmd("INSERT INTO `pages` (`domain`, `url`) VALUES ( \
                    '2', \
                    '/' \
               );")

        log("Database initialized.")
    else:
        # The database already exists.
        log("Existing database initialized.")

    # Crawling Demonstration
    crawl()