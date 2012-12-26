"""URI level tests for the sediment biophysical module"""

import unittest
import os
import subprocess
import logging
import subprocess

from osgeo import gdal
from nose.plugins.skip import SkipTest
import numpy

from invest_natcap.routing import routing
import invest_test_core

LOGGER = logging.getLogger('routing_test')

class TestRasterUtils(unittest.TestCase):
    def test_smoke_routing(self):
        base_dir = 'data/test_out/routing_test'
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        output_uri = os.path.join(base_dir, 'out.tif')
        regression_uri = 'data/routing_regression/out.tif'
        dem_uri = 'data/sediment_test_data/dem'
#        dem_uri = 'data/smooth_rasters/smoothleft.tif'
#        dem_uri = 'data/smooth_rasters/random.tif'
        aoi_uri = 'data/sediment_test_data/watersheds.shp'

        out_nodata = -1.0
        routing.calculate_routing(dem_uri, [], lambda x: x, base_dir, output_uri, out_nodata, aoi_uri = aoi_uri)

        invest_test_core.assertTwoDatasetEqualURI(self, output_uri, regression_uri)
#        subprocess.Popen(['qgis', output_uri])
