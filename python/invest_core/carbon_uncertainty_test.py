import unittest
import carbon_uncertainty
import data_handler
import numpy as np
import os
from dbfpy import dbf

try:
    from osgeo import ogr, gdal
    from osgeo.gdalconst import *
    import numpy
    use_numeric = False
except ImportError:
    import ogr, gdal
    from gdalconst import *
    import Numeric

class TestCarbonUncertainty(unittest.TestCase):
    def test_carbon_uncertainty_smoke(self):
        """Smoke test for carbon_uncertainty function.  Shouldn't crash with
        zero length inputs"""
        driver = gdal.GetDriverByName("GTIFF")
        lulc = driver.Create('../../test_data/test_blank_input', 1, 1, 1, gdal.GDT_Byte)
        lulc.GetRasterBand(1).SetNoDataValue(-1.0)

        output = driver.Create('../../test_data/test_blank_output', 1, 1, 1, gdal.GDT_Byte)
        output.GetRasterBand(1).SetNoDataValue(-1.0)

        args = { 'lulc':lulc,
                'carbon_pools': dbf.Dbf('../../test_data/test_blank_dbf', new=True),
                'output': output}
        carbon_uncertainty.execute(args)
        pass

    def test_carbon_uncertainty_with_inputs(self):
        """Test carbon_uncertainty using realistic inputs."""
        driver = gdal.GetDriverByName("GTIFF")
        lulc = gdal.Open('../../lulc_samp_cur', GA_ReadOnly)
        out_dict = {'uri':'../../carbon_output/test_real_output.tif',
                    'input':False,
                    'type': 'gdal',
                    'dataType': 6}
        output = data_handler.mimic(lulc, out_dict)
        args = { 'lulc': lulc,
                'carbon_pools': dbf.Dbf('../../test_data/carbon_pools_int.dbf'),
                'output': output}
        carbon_uncertainty.execute(args)
        output = data_handler.close(output)
        pass

    def test_build_uncertainty_pools(self):
        """Verify the correct construction of the pools dict"""
        db = dbf.Dbf('../../uncertain_carbon_pools_samp.dbf', readOnly=1)
        for type in ['L', 'A', 'H']:
            pools = carbon_uncertainty.build_uncertainty_pools_dict(db, type, 1, -1, 255)
            numRecords = db.recordCount
            poolsLen = len(pools)

            #adding one extra value to the expected length of the pools dict
            #Extra entry represents the nodata value.
            self.assertEqual(numRecords + 1, poolsLen, 'Expected ' + str(numRecords / 3) +
                             ' records in the pools dict, but found ' + str(poolsLen) + ' instead')
        pass

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCarbonUncertainty)
    unittest.TextTestRunner(verbosity=2).run(suite)

