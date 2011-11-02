import unittest
import timber

class TestInvestTimberCore(unittest.TestCase):
    def test_timber_model(self):
        args = {'output_dir': '../../test_data/timber',
                'timber_shape_uri': '../../test_data/timber/input/plantation.shp',
                'attr_table_uri': '../../test_data/timber/input/plant_table.dbf',
                'market_disc_rate': 7}

        timber.execute(args)

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestInvestTimberCore)
    unittest.TextTestRunner(verbosity=2).run(suite)
