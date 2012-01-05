import sys, imp
import os
import platform
import time

cmd_folder = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, cmd_folder + '/../invest_core')
invest_root = cmd_folder + '/../../'

if platform.system() == 'Windows':
    sys.path.append(invest_root + 'OSGeo4W/lib/site-packages')

from PyQt4 import QtGui, QtCore

import simplejson as json
#import jsonschema, warnings
from optparse import OptionParser
import base_widgets
import executor
import iui_validator

class ModelUIRegistrar(base_widgets.Registrar):
    def __init__(self):
        super(ModelUIRegistrar, self).__init__()
        
        changes = {'checkbox': CheckBox,
                   'file': base_widgets.FileEntry,
                   'folder': base_widgets.FileEntry,
                   'text': base_widgets.YearEntry
                    }
        
        self.elementMap.update(changes)
        
class ModelUI(base_widgets.RootWindow):
    def __init__(self, uri, use_gui):
        """Constructor for the DynamicUI class, a subclass of DynamicGroup.
            DynamicUI loads all setting from a JSON object at the provided URI
            and recursively creates all elements.
            
            uri - the string URI to the JSON configuration file.
            use_gui - a boolean.  Determines whether the UI will be presented
                to the user for interaction.  Necessary for testing.
            
            returns an instance of DynamicUI."""
            
        #the top buttonbox needs to be initialized before super() is called, 
        #since super() also creates all elements based on the user's JSON config
        #this is important because QtGui displays elements in the order in which
        #they are added.
        layout = QtGui.QVBoxLayout()
        
        self.links = QtGui.QLabel()
        self.links.setOpenExternalLinks(True)
        self.links.setAlignment(QtCore.Qt.AlignRight)
        layout.addWidget(self.links)
        
        registrar = ModelUIRegistrar()
        self.okpressed = False
        
        base_widgets.RootWindow.__init__(self, json.loads(uri), layout, registrar)


        self.layout().setSizeConstraint(QtGui.QLayout.SetMinimumSize)
        self.use_gui = use_gui
        
        self.initUI()
        
    def initUI(self):
        """Initialize the User Interface elements specific to this class.
            Most elements are created with the call to super() in the __init__
            function, element creation is handled in 
            DynamicGroup.createElements().
            
            returns nothing"""
        
        #set the window's title
        try:
            self.setWindowTitle(self.attributes['label'])
        except KeyError:
            self.setWindowTitle('InVEST')
        
        self.addLinks()
        
        #reveal the assembled UI to the user, but only if not testing.
        if self.use_gui:
            self.show()
        
    def addLinks(self):
        docURI = 'file:///' + os.path.abspath(invest_root +
                                     self.attributes['localDocURI'])
        self.feedbackBody="Please include the following information:\
\n\n1) InVEST model you're having difficulty with\n2) Explicit error message or \
behavior\n3) If possible, a screenshot of the state of your InVEST toolset when \
you get the error.\n4)ArcGIS version and service pack number\n\n\
Feel free to also contact us about requests for collaboration, suggestions for \
improvement, or anything else you'd like to share."
        self.feedbackURI = 'mailto:richsharp@stanford.edu?subject=InVEST Feedback'
        self.links.setText('<a href=\"' + docURI + '\">Model documentation' +
                             '</a> | <a href=\"' + self.feedbackURI + '\">'+
                             'Send feedback</a>')
        self.links.linkActivated.connect(self.contactPopup)
        
    def contactPopup(self, uri):
        if str(uri) == self.feedbackURI:
            #open up a qdialog
            self.feedbackDialog = QtGui.QMessageBox()
            self.feedbackDialog.setWindowTitle('Send feedback')
            self.feedbackDialog.setText("If you'd like to report a problem with\
this model, send an email to richsharp@stanford.edu." + self.feedbackBody)
            self.feedbackDialog.show()

        QtGui.QDesktopServices.openUrl(QtCore.QUrl(uri))
    
    def queueOperations(self):
        modelArgs = self.assembleOutputDict()
        self.operationDialog.executor.addOperation('validator', modelArgs,
                cmd_folder + '/../invest-natcap.invest-3/python/invest_core/' + self.attributes['modelName'] 
                + '_validator.py')
        self.operationDialog.executor.addOperation('model', 
                                                   modelArgs,
                                                   self.attributes['targetScript'])

            
class CheckBox(QtGui.QCheckBox, base_widgets.DynamicPrimitive):
    """This class represents a checkbox for our UI interpreter.  It has the 
        ability to enable and disable other elements."""
         
    def __init__(self, attributes):
        """Constructor for the CheckBox class.
 
            attributes - a python dictionary containing all attributes of this 
                checkbox as defined by the user in the json configuration file.
            
            returns an instance of CheckBox"""
            
#        super(CheckBox, self).__init__(attributes)
        QtGui.QCheckBox.__init__(self)
        base_widgets.DynamicPrimitive.__init__(self, attributes)

        #set the text of the checkbox
        self.setText(attributes['label'])
        
        #connect the button to the toggle function.
        self.toggled.connect(self.toggle)
        
    def toggle(self, isChecked):
        """Enable/disable all elements controlled by this element.
        
            returns nothing."""
            
        self.setState(isChecked, includeSelf=False)
        
    def isEnabled(self):
        """Check to see if this element is checked.
        
            returns a boolean"""
            
        return self.isChecked()
    
    def value(self):
        """Get the value of this checkbox.
        
            returns a boolean."""
        return self.isChecked()
    
    def setValue(self, value):
        """Set the value of this element to value.
            
            value - a string or boolean representing
            
            returns nothing"""
            
        if isinstance(value, unicode) or isinstance(value, str):
            if value == 'True':
                value = True
            else:
                value = False
                
        self.setChecked(value)
        self.setState(value, includeSelf=False)
             
    def requirementsMet(self):
        return self.value()

def validate(jsonObject):
    """Validates a string containing a JSON object against our schema.  Uses the
        JSONschema project to accomplish this. 
        
        jsonschema draft specification: 
            http://tools.ietf.org/html/draft-zyp-json-schema-03
            
        jsonschema project sites:
            http://json-schema.org/implementations.html
            http://code.google.com/p/jsonschema/
            
        arguments:
        jsonObject - a string containing a JSON object.
        
        returns nothing."""
    
    data = json.loads(jsonObject)
    
    primitives = {"type" : "object",
                 "properties": {
                    "id":{"type" : "string",
                          "optional": False},
                    "args_id": {"type" : "string",
                                "optional": True},
                    "type": {"type": "string",
                             "pattern": "^((file)|(folder)|(text)|(checkbox))$"},
                    "label": {"type": "string",
                              "optional": True},
                    "defaultValue": {"type": ["string", "number", "boolean"],
                                    "optional": True},
                    "required":{"type": "boolean",
                                "optional" : True},
                    "validText": {"type": "string",
                                  "optional": True},
                    "dataType": {"type" : "string",
                                 "optional": True},
                    "width":{"type": "integer",
                             "optional": True},
                    "requiredIf":{"type": "array",
                                  "optional": True,
                                  "items": {"type": "string"}
                                  }
                    }
                }

    lists = {"type": "object",
             "properties":{
               "id": {"type": "string",
                      "optional": False},
                "type": {"type": "string",
                         "optional": False,
                         "pattern": "^list$"},
                "elements": {"type": "array",
                             "optional": True,
                             "items": {
                               "type": primitives
                               }
                             }
               }
             }
    
    containers = {"type": "object",
                  "properties": {
                     "id": {"type": "string",
                            "optional" : False},
                     "type":{"type": "string",
                             "optional": False,
                             "pattern": "^container$"},
                     "collapsible": {"type": "boolean",
                                     "optional": False},
                     "label": {"type": "string",
                               "optional": False},
                     "elements":{"type": "array",
                                 "optional": True,
                                 "items": {
                                   "type": [lists, primitives]
                                   }
                                 }
                     }
                  }

    elements = {"type": "array",
                "optional": True,
                "items": {
                   "type":[primitives, lists, containers]
                   }
                }

#, lists, containers

    schema = {"type":"object",
              "properties":{
                "id": {"type": "string",
                       "optional": False},
                "label": {"type" : "string",
                          "optional" : False},
                "targetScript": {"type" : "string",
                                 "optional": False},
                "height": {"type": "integer",
                           "optional": False},
                "width": {"type": "integer",
                          "optional": False},
                "localDocURI": {"type": "string",
                                "optional": False},
                "elements": elements
                }
              }
    try:
        warnings.simplefilter('ignore')
        jsonschema.validate(data, schema)
    except ValueError:
        print 'Error detected in your JSON syntax: ' + str(ValueError)
        print 'Exiting.'
        sys.exit()

def getFlatDefaultArgumentsDictionary(args):
    flatDict = {}
    if isinstance(args, dict):
        if 'args_id' in args and 'defaultValue' in args:
            flatDict[args['args_id']] = args['defaultValue']
        if 'elements' in args:
            flatDict.update(getFlatDefaultArgumentsDictionary(args['elements']))
    elif isinstance(args, list):
        for element in args:
            flatDict.update(getFlatDefaultArgumentsDictionary(element))
                
    return flatDict
            

def main(json_args, use_gui=True):
    app = QtGui.QApplication(sys.argv)
#    validate(json_args)
    ui = ModelUI(json_args, use_gui)
    if use_gui == True:
        result = app.exec_()
    else:
        orig_args = json.loads(json_args)
        args = getFlatDefaultArgumentsDictionary(orig_args)

        thread = executor.Executor()
        thread.addOperation('model', args, orig_args['targetScript'])
        
        thread.start()
        
        while thread.isAlive() or thread.hasMessages():
            message = thread.getMessage()
            if message != None:
                print(message.rstrip())
            time.sleep(0.005)

if __name__ == '__main__':
    #Optparse module is deprecated since python 2.7.  Using here since OSGeo4W
    #is version 2.5.
    parser = OptionParser()
    parser.add_option('-t', '--test', action='store_false', default=True, dest='test')
    (options, args) = parser.parse_args(sys.argv)

    modulename, json_args = args

    args = open(json_args)

    main(args.read(), options.test)
    
    