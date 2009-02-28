from hashlib import md5
import os
import cherrypy
import cf

configfile = os.path.join(os.path.dirname(__file__), "../conf/mg.conf") # that's hardcoded, because this module is invoked by Apache

passwords  = {}
privileges = {}

def get_realm_hash(environ, user, realm):
	if user in passwords:
		value = md5()
		# user:realm:password
		value.update(user+":"+realm+":"+passwords[user])
		hash = value.hexdigest()
		return hash
	print >>f, "trying to authenticate user", user
	return None

ANONYMOUS = None
def get_user():
	"get authorization from apache/lighttpd/squid"
	try:
		hdr = cherrypy.request.headers['Authorization']
		start = hdr.find('Digest username="')
		end = hdr.find('"', start+17)
		return hdr[start+17:end]
	except KeyError:
		return ANONYMOUS

def get_privs(user):
	try:
		return privileges[user]
	except KeyError:
		return {}

def set_pass(user, password):
	passwords[user] = password
	
def set_priv(user, priv, value):
	if not user in privileges:
		privileges[user] = {}
	privileges[user][priv] = value

def get_current_privs():
	return get_privs(get_user())

# add users from configfile
conf = cf.parse(configfile)
users = conf.s("users") or []
for user in users.l()['sections']:
	current = users.s(user)
	set_pass(user, current.v("password"))
	privileges_dict = current.v("privs") or {}
	for key in privileges_dict:
		set_priv(user, key, privileges_dict[key])
