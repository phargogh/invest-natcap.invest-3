"""URI level tests for the sediment biophysical module"""

import unittest
import os
import subprocess
import logging

from osgeo import gdal
from osgeo import ogr
from osgeo import osr
from nose.plugins.skip import SkipTest
import numpy as np
from invest_natcap import raster_utils
import invest_test_core

LOGGER = logging.getLogger('invest_core')

class TestRasterUtils(unittest.TestCase):
    def test_reclassify_dataset(self):
        base_dir = 'data/test_out/reclassify_dataset'
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        output_uri = os.path.join(base_dir, 'reclassified.tif')
        base_uri = 'data/base_data/terrestrial/lulc_samp_cur'
        dataset = gdal.Open(base_uri)
        value_map = {1: 0.1, 2: 0.2, 3: 0.3, 4: 0.4, 5: 0.5}

        reclassified_ds = raster_utils.reclassify_dataset(
            dataset, value_map, output_uri, gdal.GDT_Float32, -1.0)

        regression_uri = 'data/reclassify_regression/reclassified.tif'
        invest_test_core.assertTwoDatasetEqualURI(self, regression_uri, output_uri)

        #If we turn on the exception flag, we should get an exception
        self.assertRaises(raster_utils.UndefinedValue,
            raster_utils.reclassify_dataset, dataset, value_map, output_uri, 
            gdal.GDT_Float32, -1.0, exception_flag = 'values_required')

    def test_gaussian_filter(self):
        base_dir = 'data/test_out/gaussian_filter'

        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        output_uri = os.path.join(base_dir, 'gaussian_filter.tif')
        base_uri = 'data/base_data/terrestrial/lulc_samp_cur'
        dataset = gdal.Open(base_uri)
        filtered_ds = raster_utils.gaussian_filter_dataset(dataset, 12.7, output_uri, -1.0)
        regression_uri = 'data/gaussian_regression/gaussian_filter.tif'
        invest_test_core.assertTwoDatasetEqualURI(self, regression_uri, output_uri)

    def test_get_rat_as_dictionary(self):
        ds = gdal.Open('data/get_rat_as_dict/activity_transition_map.tif')
        rat_dict = raster_utils.get_rat_as_dictionary(ds)

        unit_dict = {
            'Max Transition': ['agricultural_vegetation_managment', 
                               'fertilizer_management', 
                               'keep_native_vegetation', 
                               'increase_native_vegetation_assisted', 
                               'ditching', 
                               'pasture_management', 
                               'irrigation_management', 
                               'increase_native_vegetation_unassisted'], 
            'Value': [0, 1, 2, 3, 4, 5, 6, 7]}

        self.assertEqual(unit_dict, rat_dict)

    def test_unique_values(self):
        dataset = gdal.Open('data/base_data/terrestrial/lulc_samp_cur')
        unique_vals = raster_utils.unique_raster_values(dataset)
        LOGGER.debug(unique_vals)

    def test_contour_raster(self):
        base_dir = 'data/test_out/contour_raster'

        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        dem_uri = 'data/sediment_test_data/dem'
        dem_dataset = gdal.Open(dem_uri)
        output_uri = os.path.join(base_dir, 'contour_raster.tif')
        raster_utils.build_contour_raster(dem_dataset, 500, output_uri)
        regression_uri = 'data/raster_utils_data/contour_raster.tif'
        invest_test_core.assertTwoDatasetEqualURI(self, regression_uri, output_uri)

    def test_vectorize_points(self):
        base_dir = 'data/test_out/raster_utils'

        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        shape_uri = os.path.join('data', 'marine_water_quality_data', 'TideE_WGS1984_BCAlbers.shp')
        shape = ogr.Open(shape_uri)

        output_uri = os.path.join(base_dir, 'interp_points.tif')
        out_raster = raster_utils.create_raster_from_vector_extents(30, 30, gdal.GDT_Float32, -1, output_uri, shape)
        raster_utils.vectorize_points(shape, 'kh_km2_day', out_raster)
        out_raster = None
        regression_uri = 'data/vectorize_points_regression_data/interp_points.tif'

        invest_test_core.assertTwoDatasetEqualURI(self, output_uri, regression_uri)

    def test_clip_datset(self):
        base_dir = 'data/test_out/raster_utils'

        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        global_clip_regression_dataset = 'data/clip_data/global_clipped.tif'
        dem_uri = '../../invest-data/Base_Data/Marine/DEMs/global_dem'
        aoi_uri = 'data/wind_energy_data/wind_energy_aoi.shp'
        dem = gdal.Open(dem_uri)
        aoi = ogr.Open(aoi_uri)
        
        global_clip_dataset = os.path.join(base_dir, 'global_clipped.tif')
        raster_utils.clip_dataset(dem, aoi, global_clip_dataset)
        invest_test_core.assertTwoDatasetEqualURI(self, global_clip_dataset, global_clip_regression_dataset)

    def test_calculate_slope(self):
        dem_points = {
            (0.0,0.0): 50,
            (0.0,1.0): 100,
            (1.0,0.0): 90,
            (1.0,1.0): 0,
            (0.5,0.5): 45}

        n = 100

        base_dir = 'data/test_out/raster_utils'

        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        dem_uri = 'data/raster_slope_regression_data/raster_dem.tif'
        dem_dataset = gdal.Open(dem_uri)
        
        slope_uri = os.path.join(base_dir,'raster_slope.tif')
        raster_utils.calculate_slope(dem_dataset, slope_uri)

        slope_regression_uri = 'data/raster_slope_regression_data/raster_slope.tif'
        invest_test_core.assertTwoDatasetEqualURI(self, slope_uri, slope_regression_uri)

    def test_calculate_value_not_in_array(self):
        array = np.array([-1,2,5,-8,-9])
        value = raster_utils.calculate_value_not_in_array(array)
        print value
        self.assertFalse(value in array)

        array = np.array([-1,-1,-1])
        value = raster_utils.calculate_value_not_in_array(array)
        print value
        self.assertFalse(value in array)

        array = np.array([-1.1,-1.2,-1.2])
        value = raster_utils.calculate_value_not_in_array(array)
        print value
        self.assertFalse(value in array)

        ds = gdal.Open('data/calculate_value_not_in_array_regression_data/HAB_03_kelp_influence_on_shore.tif')
        value = raster_utils.calculate_value_not_in_dataset(ds)
        _, _, array = raster_utils.extract_band_and_nodata(ds, get_array = True)
        self.assertFalse(value in array)


    def test_create_rat_with_no_rat(self):
        test_out = './data/test_out/raster_utils/create_rat/'
        out_uri = os.path.join(test_out, 'test_RAT.tif')

        if not os.path.isdir(test_out):
            os.makedirs(test_out)
        
        dr = gdal.GetDriverByName('GTiff')
 
        ds = dr.Create(out_uri, 5, 5, 1, gdal.GDT_Int32)
        
        srs = osr.SpatialReference()
        srs.SetUTM(11,1)
        srs.SetWellKnownGeogCS('NAD27')
        ds.SetProjection(srs.ExportToWkt())
        ds.SetGeoTransform([444720, 30, 0, 3751320, 0 , -30])

        matrix = np.array([[1,2,3,4,5],
                           [5,4,3,2,1],
                           [3,2,4,5,1],
                           [2,1,3,4,5],
                           [4,5,1,2,3]])

        band = ds.GetRasterBand(1)
        band.SetNoDataValue(-1)
        band.WriteArray(matrix)
        band = None

        tmp_dict = {11:'farm', 23:'swamp', 13:'marsh', 22:'forest', 3:'river'}
        field_1 = 'DESC'
       
        known_results = np.array([[3, 'river'],
                                  [11, 'farm'],
                                  [13, 'marsh'],
                                  [22, 'forest'],
                                  [23, 'swamp']])

        ds_rat = raster_utils.create_rat(ds, tmp_dict, field_1)

        band = ds_rat.GetRasterBand(1)
        rat = band.GetDefaultRAT()
        col_count = rat.GetColumnCount()
        row_count = rat.GetRowCount()

        for row in range(row_count):
            for col in range(col_count):
                self.assertEqual(str(known_results[row][col]), rat.GetValueAsString(row, col))
        
        band = None
        rat = None
        ds = None
        ds_rat = None
        
    def test_get_raster_properties(self):
        """Test get_raster_properties against a known raster saved on disk"""
        data_dir = './data/raster_utils_data'
        ds_uri = os.path.join(data_dir, 'get_raster_properties_ds.tif')

        ds = gdal.Open(ds_uri)

        result_dict = raster_utils.get_raster_properties(ds)

        expected_dict = {'width':30, 'height':-30, 'x_size':1125, 'y_size':991}

        self.assertEqual(result_dict, expected_dict)

    def test_get_raster_properties_unit_test(self):
        """Test get_raster_properties against a hand created raster with set 
            properties"""
        driver = gdal.GetDriverByName('MEM')
        ds_type = gdal.GDT_Int32
        dataset = driver.Create('', 112, 142, 1, ds_type)

        srs = osr.SpatialReference()
        srs.SetUTM(11, 1)
        srs.SetWellKnownGeogCS('NAD27')
        dataset.SetProjection(srs.ExportToWkt())
        dataset.SetGeoTransform([444720, 30, 0, 3751320, 0, -30])
        dataset.GetRasterBand(1).SetNoDataValue(-1)
        dataset.GetRasterBand(1).Fill(5)
        
        result_dict = raster_utils.get_raster_properties(dataset)

        expected_dict = {'width':30, 'height':-30, 'x_size':112, 'y_size':142}

        self.assertEqual(result_dict, expected_dict)

    def test_reproject_datasource(self):
        """A regression test using some of Nicks sample data that didn't work on
            his machine"""
        
        data_dir = './data/raster_utils_data'
        barkclay_uri = os.path.join(data_dir, 'AOI_BarkClay.shp')
        lat_long_uri = os.path.join(data_dir, 'lat_long_file.shp')

        barkclay = ogr.Open(barkclay_uri)
        lat_long = ogr.Open(lat_long_uri)
        lat_long_srs = lat_long.GetLayer().GetSpatialRef()
        lat_long_wkt = lat_long_srs.ExportToWkt()

        out_dir = './data/test_out/raster_utils/reproject_datasource'
        
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)

        out_uri = os.path.join(out_dir, 'reprojected_aoi_barkclay.shp')
        regression_uri = os.path.join(data_dir, 'reprojected_aoi_barkclay.shp')

        result_ds = raster_utils.reproject_datasource(
                barkclay, lat_long_wkt, out_uri)

        result_ds = None

        invest_test_core.assertTwoShapesEqualURI(
                self, out_uri, regression_uri)

    def test_reclassify_by_dictionary(self):
        landcover_uri = 'data/pollination/samp_input/landuse_cur_200m.tif'
        out_uri = 'data/test_out/raster_utils/reclassed_lulc.tif'
        sample_ds = gdal.Open(landcover_uri)

        reclass_rules = dict((n, n**2.0) for n in range(3, 60))

        # This call will check the default case, where reclassify_by_dictionary
        # uses the given nodata value as the value if a pixel value is not
        # found in the reclass_rules dictionary.
        raster_utils.reclassify_by_dictionary(sample_ds, reclass_rules,
            out_uri, 'GTiff', -1.0, gdal.GDT_Float32)
        reg_uri = 'data/raster_utils_data/reclassed_lulc.tif'
        invest_test_core.assertTwoDatasetEqualURI(self, out_uri, reg_uri)

