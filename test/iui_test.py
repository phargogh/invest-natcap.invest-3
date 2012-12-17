import unittest
import os.path

from PyQt4 import QtGui

from invest_natcap.iui import base_widgets as base_widgets

JSON_DIR = os.path.join('data', 'iui', 'sample_json')

class ContainerTest(unittest.TestCase):
    def setUp(self):
        container_test = os.path.join(JSON_DIR, 'test_container.json')

        # NEED TO FINISH THIS CALL!
        self.app = QtGui.QApplication([])
        self.ui = base_widgets.ExecRoot(container_test)

    def test_outside_element_toglling_container(self):
        # Steps to check:
        # 0.  Verify that the container is disabled
        # 1.  Put something in the file field.
        # 2.  Verify that the container is enabled
        # 3.  Remove the contents of the file field
        # 4.  Verify that the container is disabled.

        container = self.ui.allElements['container']
        filefield = self.ui.allElements['test_file']
        print container
        print 'enabled %s' % container.isEnabled()
        #container.toggleHiding(False)
        filefield.setValue('aaa')
        print 'enabled %s' % container.isEnabled()
        print 'value %s' % filefield.value()
        print filefield.setValue('')
        print 'enabled %s' % container.isEnabled()
