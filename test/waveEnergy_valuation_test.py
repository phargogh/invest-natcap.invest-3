import os
import sys
import unittest

import numpy as np
from invest_natcap.wave_energy import waveEnergy_valuation
import invest_test_core

class TestWaveEnergyValuation(unittest.TestCase):
    def test_wave_energy_valuation_regression(self):
        """This function invokes the valuation part of the wave energy model given URI inputs.
        It will do filehandling and open/create appropriate objects to 
        pass to the core wave energy valuation processing function.  It may write
        log, warning, or error messages to stdout.
        
        args - A python dictionary with at least the following possible entries:
        args['workspace_dir'] - Where the intermediate and ouput folder/files will be saved.
        args['land_gridPts_uri'] - A CSV file path containing the Landing and Power Grid Connection Points table.
        args['machine_econ_uri'] - A CSV file path for the machine economic parameters table.
        args['number_of_machines'] - An integer specifying the number of machines.
        args['projection_uri'] - A path for the projection to transform coordinates from decimal degrees to meters.
        args['globa_dem'] - We need the depth of the locations for calculating costs.
        args['']
        """
        
        args = {}
        args['workspace_dir'] = './data/test_data/wave_Energy'
        args['wave_base_data_uri'] = './data/test_data/wave_Energy/samp_input/WaveData'
        args['land_gridPts_uri'] = './data/test_data/wave_Energy/samp_input/LandGridPts_WCVI_CSV.csv'
        args['machine_econ_uri'] = './data/test_data/wave_Energy/samp_input/Machine_PelamisEconCSV.csv'
        args['number_of_machines'] = 28
        args['projection_uri'] = './data/test_data/wave_Energy/test_input/WGS_1984_UTM_Zone_10N.prj'
        args['global_dem'] = './data/test_data/wave_Energy/samp_input/global_dem'
        args['wave_data_shape_path'] = './data/test_data/wave_Energy/Intermediate/WaveData_clipZ.shp'
        
        waveEnergy_valuation.execute(args)

        #assert that the output raster is equivalent to the regression
        #test
        invest_test_core.assertTwoDatasetEqualURI(self,
            args['workspace_dir'] + '/Output/npv_usd.tif',
            args['workspace_dir'] + '/regression_tests/npv_usd_regression.tif')

        #Need to check the shapefiles landingpoints and gridpoint to make sure
        #those are both correct
        #Check that output/intermediate files have been made
        regression_landing_shape = ogr.Open(args['workspace_dir'] + '/regression_tests/LandPts_prj_regression.shp')
        landing_shape = ogr.Open(args['workspace_dir'] + '/Output/LandPts_prj.shp')
        
        regression_layer = regression_landing_shape.GetLayer(0)
        layer = landing_shape.GetLayer(0)
        
        regression_feat_count = regression_layer.GetFeatureCount()
        feat_count = layer.GetFeatureCount()
        self.assertEqual(regression_feat_count, feat_count)
        
        layer_def = layer.GetLayerDefn()
        reg_layer_def = regression_layer.GetLayerDefn()
        field_count = layer_def.GetFieldCount()
        reg_field_count = reg_layer_def.GetFieldCount()
        self.assertEqual(field_count, reg_field_count, 'The shapes DO NOT have the same number of fields')
        
        reg_feat = regression_layer.GetNextFeature()
        feat = layer.GetNextFeature()
        while reg_feat is not None:            
            for fld_index in range(field_count):
                field = feat.GetField(fld_index)
                reg_field = reg_feat.GetField(fld_index)
                self.assertEqual(field, reg_field, 'The field values DO NOT match')
            feat.Destroy()
            reg_feat.Destroy()
            feat = layer.GetNextFeature()
            reg_feat = regression_layer.GetNextFeature()
            
        regression_landing_shape.Destroy()
        landing_shape.Destroy()
        
        
        regression_grid_shape = ogr.Open(args['workspace_dir'] + '/regression_tests/GridPt_prj_regression.shp')
        grid_shape = ogr.Open(args['workspace_dir'] + '/Output/GridPt_prj.shp')
        
        regression_layer = regression_grid_shape.GetLayer(0)
        layer = grid_shape.GetLayer(0)
        
        regression_feat_count = regression_layer.GetFeatureCount()
        feat_count = layer.GetFeatureCount()
        self.assertEqual(regression_feat_count, feat_count)
        
        layer_def = layer.GetLayerDefn()
        reg_layer_def = regression_layer.GetLayerDefn()
        field_count = layer_def.GetFieldCount()
        reg_field_count = reg_layer_def.GetFieldCount()
        self.assertEqual(field_count, reg_field_count, 'The shapes DO NOT have the same number of fields')
        
        reg_feat = regression_layer.GetNextFeature()
        feat = layer.GetNextFeature()
        while reg_feat is not None:            
            for fld_index in range(field_count):
                field = feat.GetField(fld_index)
                reg_field = reg_feat.GetField(fld_index)
                self.assertEqual(field, reg_field, 'The field values DO NOT match')
            feat.Destroy()
            reg_feat.Destroy()
            feat = layer.GetNextFeature()
            reg_feat = regression_layer.GetNextFeature()
            
        regression_grid_shape.Destroy()
        grid_shape.Destroy()
