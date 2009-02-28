import os

import cherrypy

from sqlalchemy import create_engine
from sqlalchemy import Table, Column, MetaData
from sqlalchemy import Integer, SmallInteger, Unicode, UnicodeText, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from genshi.template import TemplateLoader

import cf
import auth

class _empty():
	pass

Base = declarative_base()
class ZT(Base):
	__tablename__ = "zt"
	id		= Column(Integer, primary_key = True)
	data	= Column(UnicodeText)
	comment	= Column(UnicodeText)
	solved	= Column(Boolean)
	
	def __init__(self, data, comment = "", solved = False):
		self.data = data
		self.comment = comment
		self.solved = solved
	
	def __repr__(self):
		return "<ZT('%s','%s','%s')>" % (self.data, self.comment, str(self.solved))
		
class Quest(Base):
	__tablename__ = "quests"
	id		= Column(Integer, primary_key = True)
	name	= Column(Unicode(128))
	ap		= Column(Integer)
	cl		= Column('class', SmallInteger)
	attr	= Column(Unicode(32))
	level	= Column(Integer)
	mage	= Column(Unicode(32))
	solved	= Column(Boolean)
	
	walkthrough = Column(UnicodeText)
	def __init__(self, name, ap, cl, level, mage, attr = None, solved = False, walkthrough = None):
		self.name	= name
		self.ap		= ap
		self.cl		= cl
		self.level	= level
		self.mage	= mage
		self.attr	= attr
		self.solved	= solved
		self.walkthrough = walkthrough
	
	def __repr__(self):
		return '<Quest named "'+self.name+'">'
		
class BaseSite(object):
	db = _empty()
	db.username = "changeme"
	db.password = "changemetoo"
	db.host	 = "localhost"
	db.port	 = 5432
	db.database = "changemeaswell"
	db.schema   = "public"
	
	def __init__(self, config):
		self.conf = cf.parse(config)
		if self.conf:
			for key in ["username", "password", "host", "port", "database", "schema"]:
				setattr(self.db, key, self.conf.v(key) or getattr(self.db, key))
		self.engine_Unicode = "postgres://"
		self.engine_Unicode += self.db.username+":"+self.db.password+"@"+self.db.host+":"+str(self.db.port)
		self.engine_Unicode += "/"+self.db.database
		self.engine = create_engine(self.engine_Unicode)
		Session = sessionmaker(bind=self.engine)
		self.session = Session()
		self.loader = TemplateLoader(
			os.path.join(os.path.dirname(__file__), 'templates'),
			auto_reload=True
		)
	def content_type(self):
		xhtml = "application/xhtml+xml"
		if os.environ.get('HTTP_ACCEPT', '').find('application/xhtml+xml') == -1:
			xhtml = "text/html"
		cherrypy.response.headers['Content-Type'] = xhtml+"; Charset=UTF-8"
		
class InheritingSite(object):
	def __init__(self, base):	
		self.base = base
		
class ZTSite(InheritingSite):
	def index(self, showsolved = None):
		self.base.content_type()
		tmpl = self.base.loader.load("zt.html")
		return tmpl.generate(zt=self.base.session.query(ZT), showsolved=showsolved=="showsolved").render('xhtml', doctype='xhtml')
	index.exposed = True
	def oneliner(self, id=0):
		try:
			id = int(id)
		except ValueError:
			id = 0
		if not id:
			return "Which poem?"
		poem = self.base.session.query(ZT).filter(ZT.id == id).first()
		if not poem:
			return "No such poem."
		else:
			return " ".join([s.strip() for s in poem.data.splitlines()])
	oneliner.exposed = True
	
class QuestSite(InheritingSite):
	column_list = ["id", "name", "ap", "class", "attr", "level", "mage", "solved"]
	
	class WalkthroughSite(object):
		def __init__(self, super):
			self.super = super
			self.base = super.base
			
		def is_authed(self):
			"Return if the user doing the current request is authenticated"
			try:
				return auth.get_current_privs()['walkthrough']
			except KeyError:
				return False
			
		def get_quest(self, id):
			try:
				id = int(id)
			except TypeError, ValueError:
				id = 0
			if not id:
				return None
			quest = self.base.session.query(Quest).filter(Quest.id == id).first()
			if not quest:
				return False
			return quest
		
		def backlink(self, id=None):
			anchor = ""
			if id:
				anchor = "#quest_"+str(id)
			return '<a href="/mg/quests/'+anchor+'">Back.</a>'
			
		def edit(self, id = None, text = None, solved = False):
			if not self.is_authed():
				return "Not authenticated." # TODO: nicer
			quest = self.get_quest(id)
			if not quest: # None or False
				return "No such quest." # TODO: nicer
			walkthrough = ""
			if quest.walkthrough:
				walkthrough = quest.walkthrough
			if text or text == "":
				if type(text) == str:
					quest.walkthrough = text.decode("utf-8")
					# must be utf8 as content_type() delivers the form as utf8
				elif type(text) == unicode:
					quest.walkthrough = text
				else:
					return "Data not entered. "+self.backlink(id) #TODO nicer
				quest.solved = not not text # returns True if text is not ""
				if text == "":
					quest.solved = not not solved
				self.base.session.commit()
				return "Entered data. "+self.backlink(id) #TODO nicer
			else:
				self.base.content_type()
				tmpl = self.base.loader.load("walkthrough/edit.html")
				return tmpl.generate (quest=quest, walkthrough=quest.walkthrough, authed=self.is_authed()).render('xhtml', doctype='xhtml')
		edit.exposed = True
		
		def default(self, id=0):
#			if not self.is_authed():
#				return "Not authenticated." # TODO: nicer
			quest = self.get_quest(id)
			if quest == None:
				return "Which walkthrough?"
			if not quest or not quest.walkthrough:
				return "No such walkthrough."
			self.base.content_type()
			tmpl = self.base.loader.load("walkthrough/view.html")
			return tmpl.generate (quest=quest, walkthrough=quest.walkthrough, authed=self.is_authed()).render('xhtml', doctype='xhtml')
		default.exposed = True

	def __init__(self, base):
		InheritingSite.__init__(self, base)
		self.walkthrough = self.WalkthroughSite(self)
		self.walkthrough.exposed = True
	
	def index(self, order_by = "id"):
		self.base.content_type()
		
		if not order_by in self.column_list:
			order_by = "id"
		
		quests = self.base.session.query(Quest).order_by(order_by)
		
		tmpl = self.base.loader.load("quest.html")
		return tmpl.generate(quests=quests, authed=self.walkthrough.is_authed()).render('xhtml', doctype='xhtml')
	index.exposed = True
		
	
site = BaseSite(os.path.join(os.path.dirname(__file__), "../conf/mg.conf"))
site.zt 	= ZTSite(site)
site.quests = QuestSite(site)
