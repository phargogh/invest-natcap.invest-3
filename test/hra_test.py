'''This will be the test module for the non-core portion of Habitat Risk
Assessment.'''

import os
import unittest
import logging

import invest_test_core

from invest_natcap.habitat_risk_assessment import hra
from invest_natcap.habitat_risk_assessment import hra_core

LOGGER = logging.getLogger('hra_test')
logging.basicConfig(format='%(asctime)s %(name)-15s %(levelname)-8s \
    %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

class TestHRA(unittest.TestCase):

    def setUp(self):

        args = {}
        args['workspace_dir'] = './data/test_out/HRA' 
        args['habitat_dir'] = './data/test_out/HRA/Input/HabitatLayers'
        args['stressors_dir'] = './data/test_out/HRA/Input/Stressors'

        args['grid_size'] = 500
        args['risk_eq'] = 'Euclidean'

        #Want to have some pairs that don't include some stressors to make sure
        #that the model can handle some things not being included all of the time.
        args['ratings'] = {
            ('kelp', 'FinfishAquacultureComm'): {'E':
                    {'Spatial Overlap': {'Rating': 2.0, 'DQ': 1.0, 'Weight': 1.0},
                    'Overlap Time': {'Rating': 1.0, 'DQ': 3.0, 'Weight': 2.0},
                    #This 0.0 in the weight should remove it from the equation
                    'Intensity': {'Rating': 3.0, 'DQ': 2.0, 'Weight' : 0.0},
                    'Management Effectiveness':  {'Rating': 1.0, 'DQ': 2.0, 'Weight' : 1.0}},
                'C': {'Change in Area':  {'Rating': 3.0, 'DQ': 1.0, 'Weight' : 2.0},
                    'Change in Structure': {'Rating': 2.0, 'DQ': 1.0, 'Weight' : 1.0},
                    'Frequency of Disturbance':{'Rating': 1.0, 'DQ': 1.0, 'Weight' : 1.0},
                    #Here would be the biotic stressors. But need to figure out
                    #how to know difference between biotic and abiotic. Could
                    #just put the impetus on the user.
                    }
                }
           }
        args['buffer_dict'] = {'FinfishAquacultureComm': 200}

        self.args = args
    
    def test_run(self):
        
        hra.execute(self.args)

'''    def test_dict(self):

        #Need to make a copy so that we have something to pass when we check
        #out the raster dictionary creation by itself. However, we have to run
        #the whole thing first so that the rasterized versions of the shapefiles
        #exist in the first place.
        dict_orig = copy.deepcopy(self.args['ratings'])

        #This is just checking whether or not it is erroring anywhere in HRA
        hra.execute(self.args)
        
        #This should pull out the ratings dictionary, and check it against our
        #pre-populated one with the open raster datasets. Need to do a 
        #dictionary check and a raster compare.
        inter_dir = os.path.join(self.args['workspace_dir'], 'Intermediate')
        h_dir = os.path.join(inter_dir, 'Habitat_Rasters')
        s_dir = os.path.join(inter_dir, 'Stressor_Rasters')
        
        model_raster_dict = hra.combine_hs_rasters(inter_dir, h_dir, s_dir, dict_orig)

        #test_raster_dict = INSERT PRE-CREATED DICTIONARY HERE '''
