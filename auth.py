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
    def __init__(self, _id, password, privileges):
        self._id = _id
        self.password = password
        self.privileges = privileges

server = Server(config['url'])
db_name = config['database']['users']
users = map(server[db_name])
users.add(User)

def get_realm_hash(environ, user_name, realm):
    try:
        # user:realm:password
        user = users[user_name]
        try:
            return user.hashes[realm]
        except (KeyError, AttributeError):
            value = md5()
            try:
                value.update(':'.join([user_name, realm, user.password]))
            except AttributeError:
                return None
            hash = value.hexdigest()
            try:
                user.hashes[realm] = hash
            except AttributeError:
                user.hashes = {realm: hash}
            users[user_name] = user
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
