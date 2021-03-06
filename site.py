import os

import cherrypy
from reprconf import Config

from couchdbkit import *
from couchdbkit_mapper import *

from genshi.template import TemplateLoader

import auth
from auth import current_user

def make_couchdb_server(url, username=None, password=None):
    # TODO: implement authentication
    return Server(url)
    
class _Empty(object):
    pass

class ZT(object):
    def __init__(self, data, comment="", solved=False):
        self.data = data
        self.comment = comment
        self.solved = solved
    
    def __repr__(self):
        return "<ZT(%s,%s,%s)>" % (repr(self.data), repr(self.comment), repr(self.solved))
        
class Quest(object):
    def __init__(self, name, ap, cl, level, mage, attr = None, solved = False, walkthrough = None):
        self.name = name
        self.points = ap
        self.class_ = cl
        self.level = level
        self.mage = mage
        self.attribute = attr
        self.solved = solved
        self.walkthrough = walkthrough
    
    def __repr__(self):
        return 'Quest(%s,%s,%s,%s,%s,%s,%s,%s)' % (repr(self.name), repr(self.points), repr(self.class_), repr(self.level), repr(self.mage), repr(self.attribute), repr(self.solved), repr(self.walkthrough))
        
class BaseSite(object):
    config = Config({
        'couch': {
            'url': 'http://localhost:5984',
            'user': None,
            'password': None,
            'database': {'quests': 'quests', 'zt': 'zt'}
        }
    })
    
    def __init__(self, config_file):
        another_config = Config(config_file)
        try:
            self.config['couch'].update(another_config['couch'])
        except KeyError:
            pass
        self.config = self.config['couch']
        self.server = make_couchdb_server(
            self.config['url'],
            self.config['user'],
            self.config['password'])
        self.db = _Empty()
        self.db.quests = map(self.server[self.config['database']['quests']])
        self.db.quests.add(Quest)
        self.db.zt = map(self.server[self.config['database']['zt']])
        self.db.zt.add(ZT)
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
    def zt_list(self, show_solved):
        self.base.content_type()
        tmpl = self.base.loader.load("zt.html")
        return tmpl.generate(
                zt=self.base.db.zt.all_docs(include_docs=True),
                showsolved=show_solved
            ).render('xhtml', doctype='xhtml')
    
    @cherrypy.expose
    def index(self):
        return self.zt_list(show_solved=False)
    
    @cherrypy.expose
    def showsolved(self):
        return self.zt_list(show_solved=True)

    def oneliner(self, id=None):
        if id is None:
            return "Which poem?"
        try:
            poem = self.base.db.zt[id]
        except ResourceNotFound:
            return "No such poem."
        else:
            return " ".join([s.strip() for s in poem.data.splitlines()])
    oneliner.exposed = True
    
class QuestSite(InheritingSite):
    class WalkthroughSite(object):
        def __init__(self, super):
            self.super = super
            self.base = super.base
            
        def is_authed(self):
            "Return if the user doing the current request is authenticated"
            try:
                return auth.users[current_user()].privileges['walkthrough']
            except (ResourceNotFound, KeyError, AttributeError):
                return False
            
        def get_quest(self, id):
            try:
                quest = self.base.db.quests[id]
            except ResourceNotFound:
                return False
            else:
                return quest
        
        def backlink(self, id=None):
            anchor = ""
            if id:
                anchor = "#quest_"+str(id)
            return '<a href="/mg/quests/'+anchor+'">Back.</a>'
            
        def edit(self, id=None, text=None, solved=False):
            if not self.is_authed():
                return "Not authenticated." # TODO: nicer
            quest = self.get_quest(id)
            if not quest: # None or False
                return "No such quest." # TODO: nicer
            walkthrough = ""
            if hasattr(quest, 'walkthrough') and quest.walkthrough:
                walkthrough = quest.walkthrough
            if text:
                if type(text) == str:
                    quest.walkthrough = text.decode("utf-8")
                    # must be utf8 as content_type() delivers the form as utf8
                elif type(text) == unicode:
                    quest.walkthrough = text
                else:
                    return "Data not entered. "+self.backlink(id) #TODO nicer
                quest.solved = solved
                self.base.db.quests.save_doc(quest)
                return "Entered data. "+self.backlink(id) #TODO nicer
            elif text == "":
                if solved != quest.solved:
                    quest.solved = solved
                try:
                    del(quest.walkthrough)
                except AttributeError:
                    pass
                self.base.db.quests.save_doc(quest)
                return "Changed data. "+self.backlink(id) #TODO nicer
            else:
                self.base.content_type()
                tmpl = self.base.loader.load("walkthrough/edit.html")
                return tmpl.generate (quest=quest, walkthrough=walkthrough, authed=self.is_authed()).render('xhtml', doctype='xhtml')
        edit.exposed = True
        
        def default(self, id=None):
#           if not self.is_authed():
#               return "Not authenticated." # TODO: nicer
            quest = self.get_quest(id)
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
    
    def index(self, order_by="level"):
        # TODO: make views!
        self.base.content_type()
        
        try:
            quests = self.base.db.quests.view('/'.join(['by', order_by]))
        except ResourceNotFound:
            quests = self.base.db.quests.all_docs(include_docs=True)
        
        tmpl = self.base.loader.load("quest.html")
        return tmpl.generate(quests=quests, authed=self.walkthrough.is_authed()).render('xhtml', doctype='xhtml')
    index.exposed = True
        
    
site = BaseSite(os.path.join(os.path.dirname(__file__), "../conf/mg.conf"))
site.zt     = ZTSite(site)
site.quests = QuestSite(site)
