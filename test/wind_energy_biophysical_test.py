"""URI level tests for the wind_energy biophysical module"""

import os, sys
from osgeo import gdal
import unittest
from nose.plugins.skip import SkipTest

from invest_natcap.wind_energy import wind_energy_biophysical
import invest_test_core

class TestWindEnergyBiophysical(unittest.TestCase):
    def test_wind_energy_biophysical(self):
        """Doc String"""

        # start making up some tests
        input_dir = './data/wind_energy_data/'
        bathymetry_uri = \
            '../../invest-data/Base_Data/Marine/DEMs/global_dem/hdr.adf'
        global_land_uri = \
                '../../invest-data/Base_Data/Marine/Land/global_polygon.shp'
        output_dir = './data/test_out/wind_energy/'

        if not os.path.isdir(output_dir):
            os.path.mkdir(output_dir)

        args = {}
        args['workspace_dir'] = output_dir
        args['aoi_uri'] = os.path.join(input_dir, 'reprojected_distance_aoi.shp')
        args['bathymetry_uri'] = bathymetry_uri
        #args['bottom_type_uri'] = os.path.join(input_dir, 'reprojected_distance_aoi.shp')
        args['hub_height']  = 50 
        args['pwr_law_exponent'] = 0.11
        args['cut_in_wspd'] = 4.0
        args['rated_wspd'] = 14.0
        args['cut_out_wspd'] = 25.0
        args['turbine_rated_pwr'] = 3.6
        args['exp_out_pwr_curve'] = 2 
        args['num_days'] = 365
        args['air_density'] = 1.225 
        args['min_depth'] = 20
        args['max_depth'] = 80
        args['min_distance'] = 7000
        args['max_distance'] = 10000
        args['land_polygon_uri'] = global_land_uri

        wind_energy_biophysical.execute(args)

    def test_wind_energy_biophysical_check_datasource_projections(self):
        
        # load a properly projected datasource and check that it passes
        datasource_uri = './data/wind_energy_data/reprojected_distance_aoi.shp'
        datasource = ogr.Open(datasource_uri)

        result = \
                wind_energy_biophysical.check_datasource_projections([datasource])

        self.assertTrue(result)
    
    def test_wind_energy_biophysical_check_datasource_projections_fail(self):
        
        # load a couple datasources and check that one fails
        ds_one_uri = './data/wind_energy_data/reprojected_distance_aoi.shp'
        ds_two_uri = './data/wind_energy_data/wind_energy_distance_aoi.shp'
        ds_one = ogr.Open(ds_one_uri)
        ds_two = ogr.Open(ds_two_uri)

        result = wind_energy_biophysical.check_datasource_projections(
                [ds_one, ds_two])

        self.assertTrue(not result)

    def test_wind_energy_biophysical_read_wind_data(self):

        wind_data_uri = './data/wind_energy_data/small_wind_data_sample.txt'

        expected_dict = {}

        expected_dict['1'] = {'LONG': -97.333330, 'LATI':26.800060,
                              'Ram-020m':6.800060, 'Ram-030m':7.196512,
                              'Ram-040m':7.427887, 'Ram-050m':7.612466, 
                              'K-010m':2.733090}
        expected_dict['2'] = {'LONG': -97.333330, 'LATI':26.866730,
                              'Ram-020m':6.910594, 'Ram-030m':7.225791,
                              'Ram-040m':7.458108, 'Ram-050m':7.643438, 
                              'K-010m':2.732726}

        results = wind_energy_biophysical.read_wind_data(wind_data_uri)

        self.assertEqual(expected_dict, results)

    def test_wind_energy_biophysical_wind_data_to_point_shape(self):
        
        regression_shape_uri = \
            './data/wind_energy_regression_data/wind_data_to_point_shape.shp'

        output_dir = './data/test_out/wind_energy/wind_data_to_point_shape/'
        
        if not os.path.isdir(output_dir):
            os.mkdir(output_dir)

        out_uri = os.path.join(output_dir, 'wind_data_shape.shp'

        expected_dict = {}

        expected_dict['1'] = {'LONG': -97.333330, 'LATI':26.800060,
                              'Ram-020m':6.800060, 'Ram-030m':7.196512,
                              'Ram-040m':7.427887, 'Ram-050m':7.612466, 
                              'K-010m':2.733090}
        expected_dict['2'] = {'LONG': -97.333330, 'LATI':26.866730,
                              'Ram-020m':6.910594, 'Ram-030m':7.225791,
                              'Ram-040m':7.458108, 'Ram-050m':7.643438, 
                              'K-010m':2.732726}

        _ = wind_energy_biophysical.wind_data_to_point_shape(
                expected_dict, 'wind_points', out_uri)        

        invest_test_core.assertTwoShapesEqualURI(self, regression_shape_uri, out_uri)
