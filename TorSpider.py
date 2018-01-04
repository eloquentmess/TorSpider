#!/usr/bin/env python
# -*- coding: utf-8 -*-

''' TorSpider – A script to explore the darkweb.
    -------------------by Christopher Steffen---
    
    Usage: TorSpider.py [Seed URL]
    
        If no Seed URL is provided, TorSpider will begin scanning wherever
        it left off last time, then will re-scan all known URLs from the top
        of the list.
    
    --------------------------------------------
    
    TorSpider will explore the darkweb to discover as many onion sites as
    possible, storing them all in a database along with whatever additional
    information can be found. It will also store data regarding which sites
    connected to which other sites, allowing for some relational mapping.
    
    The database generated by TorSpider will be accessible via a secondary
    script which will create a web interface for exploring the saved data.
'''

'''---INCLUDES---'''

import requests, sys, sqlite3 as sql
from HTMLParser import HTMLParser

'''---VARIABLES---'''

# How many threads do we want the spider to run on this system?
max_threads     = 5 # Five threads shouldn't be too heavy a load, even for a Pi.
recursion_depth = 1 # How many links deep should we delve into any particular URL? 0 = just parse the page provided, don't follow internal links.

'''---CLASSES---'''

class parse_links(HTMLParser):
    # Parse given HTML for all a.href and img.src links.
    def __init__(self):
        HTMLParser.__init__(self)
        self.output_list = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.output_list.append(dict(attrs).get('href'))
        elif tag == 'img':
            self.output_list.append(dict(attrs).get('src'))

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

'''---FUNCTIONS---'''

def get_links(data):
    # Given HTML input, return a list of all unique links.
    p = parse_links()
    p.feed(data)
    links = []
    for link in p.output_list:
        if(link != None):
            links.append(link)
    return list(set(links))

def get_title(data):
    # Given HTML input, return the title of the page.
    p = parse_title()
    p.feed(data)
    return p.title

def get_domain(link):
    # Given a link, extract the domain.
    s = link.split('/')
    for i in s:
        if(i != 'http:' and i != 'https:' and i != ''):
            return i

def get_unique_domains(links):
    # Given HTML input, return a list of all unique domains.
    domains = []
    for link in links:
        domains.append(get_domain(link))
    return list(set(domains))

def get_tor_session():
    # Create a session that's routed through Tor.
    session = requests.session()
    session.proxies = {'http': 'socks5://127.0.0.1:9050', 'https':'socks5://127.0.0.1:9050'}
    return session

def get_onion_domains(domains):
    # Get a list of onion-specific domains from a list of various domains.
    onions = []
    for domain in domains:
        if('.onion' in domain):
            onions.append(domain)
    return onions

def db_cmd(cmd):
    # This function executes commands in the database.
    rtn = None
    con = sql.connect('SpiderWeb.db')
    cur = con.cursor()
    try:
        buf = cmd.strip()
        cur.execute(buf)
        if(buf.upper().startswith("SELECT")):
            rtn = cur.fetchall()
    except sql.Error as e:
        print("SQL ERROR -- %s" % (e))
    con.commit()
    con.close()
    if(rtn != None):
        try:
            (rtn, ) = rtn[0]
        except:
            rtn = None
    return rtn

def crawl(url, depth = recursion_depth):
    ''' This is the primary spider function. Given a URL, it'll collect information on the
        page and crawl along all links, adding external URLs to one database and crawling
        up to recursion_depth levels deep scanning for new URLs within this TLD.
    '''
    target = get_domain(url)        # Find the local TLD.
    try:
        data = session.get(url).text    # Grab the HTML from the provided URL.
    except:
        # Couldn't grab the data.
        print "Error retrieving %s" % (url)
        if(depth != recursion_depth):
            # We're in a sub-loop, and we need to return two arrays to exit gracefully.
            return ([], [])
        else:
            sys.exit(0)
    site_links = get_links(data)    # Strip the links from the provided URL.
    intlinks = []   # Internal links.
    extlinks = []   # External links.
    
    #Sort links into internal and external.
    for link in site_links:
        if(link[0] == '/'):
            new_link = 'https://' if 'https' in url else 'http://'
            new_link += target + link
            intlinks.append(new_link)
        elif('://' in link and 'http' in link): # We only want http:// or https://
            if(get_domain(link) == target):
                intlinks.append(link)
            else:
                extlinks.append(link)
    
    # We now have the page title, TLD, and lists of internal and external links.
    if(depth > 0):
        # We've still got some recursion to do.
        i_links = []
        e_links = []
        for link in intlinks:
            # Crawl each internal link on the page, adding the returned int and ext links to arrays.
            ''' NOTE: We will want to devise a way to prevent crawling the same page multiple times, to save time. Store crawled pages in the DB. '''
            (i, e) = crawl(link, depth - 1)
            i_links += i
            e_links += e
        # Next, add the crawled int and ext link arrays to this loop's int and ext link arrays, then return them.
        intlinks = list(set(intlinks + i_links)) # Add the lists without duplicates.
        extlinks = list(set(extlinks + e_links)) # Add the lists without duplicates.
    if(depth != recursion_depth):
        # This wasn't the top-level crawl, so return the results of the hunt.
        #print "Link scanned: %s" % (url)
        return (intlinks, extlinks)
    
    domains = get_unique_domains(extlinks)  # Get a list of external domains discovered.
    page_title = get_title(data)            # Grab the page title from the HTML.
    onions = get_onion_domains(domains)     # Get a list of onion-specific domains.
    
    print "Site scan complete.\n" + ('-' * 79)
    print "Seed URL:          %s" % (url)
    print "Title:             %s" % (page_title)
    print "Internal links:    %i" % (len(intlinks))
    print "External links:    %i" % (len(extlinks))
    print "TLDs discovered:   %i" % (len(domains))
    print "Onions discovered: %i" % (len(onions))
    
    f = open('intlinks.txt','wb')
    f.write(u'\n'.join(intlinks).encode('utf-8').strip())
    f.close()
    f = open('extlinks.txt','wb')
    f.write(u'\n'.join(extlinks).encode('utf-8').strip())
    f.close()
    f = open('domains.txt','wb')
    f.write(u'\n'.join(domains).encode('utf-8').strip())
    f.close()
    f = open('onions.txt','wb')
    f.write(u'\n'.join(onions).encode('utf-8').strip())
    f.close()
    

'''---PREPARATION---'''

# Create a new Tor session.
session = get_tor_session()

# Just to prevent some SSL errors.
requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += ':ECDHE-ECDSA-AES128-GCM-SHA256'

# Spoof a specific user agent (tor browser).
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; rv:52.0) Gecko/20100101 Firefox/52.0'})

# Determine if the user has provided a Seed URL or asked for usage information.
seed_url = 'http://zqktlwi4fecvo6ri.onion/wiki/Main_Page' # This is the Uncensored Hidden Wiki URL
try:
    seed_url = sys.argv[1]
except:
    pass
if(seed_url == '--help' or seed_url == '-h'):
    print '''
Usage: TorSpider.py [Seed URL]

    If no Seed URL is provided, TorSpider will begin scanning wherever
    it left off last time, then will re-scan all known URLs from the top
    of the list.
'''
    sys.exit(0)

# First, let's see if we're able to connect through Tor.
try:
    local_ip = requests.get('http://icanhazip.com').text
    tor_ip = session.get('http://icanhazip.com').text
    if(local_ip != tor_ip):
        print "Connected to Tor. Scanning %s...\nRecursion depth set to %i." % (seed_url, recursion_depth)
    else:
        print "Tor connection unsuccessful."
        sys.exit(0)
except:
    print "Tor connection unsuccessful."
    sys.exit(0)

'''---SQL INITIALIZATION---'''

'''
# The following two databases are constant. They store the current state of the spider and a list of all TLDs we've discovered so far.
# Additional tables will be created for each specific onion domain in which pages and links to other TLDs will be stored.

# The 'onions' database stores a list of all TLDs, including their id, domain, last online status, and the number of times they've been seen offline.
db_cmd('CREATE TABLE IF NOT EXISTS `onions` (`id` INTEGER PRIMARY KEY,`domain` TEXT, `online` INTEGER, `offline_count` INTEGER, `info` TEXT);')

# The `state` database keeps certain information about the last run, so we can pick up on reboot.
db_cmd('CREATE TABLE IF NOT EXISTS `state` (`last_id` INTEGER);')
'''

'''---MAIN---'''

crawl(seed_url)