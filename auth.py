import os
from hashlib import md5

import cherrypy
from reprconf import Config

from couchdbkit import *
from couchdbkit_mapper import *

config_file = os.path.join(os.path.dirname(__file__), "../conf/mg.conf") # that's hardcoded, because this module is invoked by Apache
config = Config({
    'couch': {
        'url': 'http://localhost:5984',
        'user': None,
        'password': None,
        'database': {'quests': 'quests', 'zt': 'zt', 'users': 'users'}
    }
})

another_config = Config(config_file)
try: 
    config['couch'].update(another_config['couch'])
except KeyError:
    pass
config = config['couch']

class User(object):
    def __init__(self, name, password, privileges):
        self.name = name
        self.password = password
        self.privileges = privileges

server = Server(config['url'])
db_name = config['database']['users']
users = map(server[db_name])
users.add(User)

def get_realm_hash(environ, user, realm):
    print >>f, "trying to authenticate user", user
    value = md5()
    try:
        # user:realm:password
        value.update(user+":"+realm+":"+users[user].password)
        hash = value.hexdigest()
        return hash
    except ResourceNotFound:
        return None

ANONYMOUS = None
def current_user():
    "get authorization from apache/lighttpd/squid"
    try:
        hdr = cherrypy.request.headers['Authorization']
        start = hdr.find('Digest username="')
        end = hdr.find('"', start+17)
        return hdr[start+17:end]
    except KeyError:
        return ANONYMOUS
