import unittest

from invest_natcap.iui import iui_validator

TEST_DATA = 'data/'

class CheckerTester(unittest.TestCase):
    def check(self):
        return self.checker.run_checks(self.validate_as)

    def assertNoError(self):
        error = self.check()
        if error != None:
            self.assertEqual(error, '')

    def assertError(self):
        error = self.check()
        self.assertNotEqual(error, '')
        self.assertNotEqual(error, None)

class FileCheckerTester(CheckerTester):
    def setUp(self):
        self.validate_as = {'type': 'file',
                            'value': TEST_DATA + 'iui/text_test.txt'}
        self.checker = iui_validator.FileChecker()

    def test_uri_exists(self):
        self.assertNoError()

    def test_nonexistent_uri(self):
        #this should fail, so we check that an error message is there.
        self.validate_as['value'] += 'a'
        self.assertError()


class FolderCheckerTester(CheckerTester):
    def setUp(self):
        self.validate_as = {'type': 'folder',
                       'value': TEST_DATA}
        self.checker = iui_validator.FolderChecker()

    def test_folder_exists(self):
        self.assertNoError()

    def test_not_folder(self):
        self.validate_as['value'] += 'a'
        self.assertError()


class OGRCheckerTester(CheckerTester):
    def setUp(self):
        self.validate_as = {'type':'OGR',
                            'value':TEST_DATA +
                            '/wave_energy_data/samp_input/AOI_WCVI.shp'}
        self.checker = iui_validator.OGRChecker()

    def test_file_layers(self):
        layer = {'name': {'inheritFrom': 'file'}}
        self.validate_as['layers'] = [layer]

        incremental_additions = [('name', {'inheritFrom': 'file'}),
                                 ('type', 'polygons'),
                                 ('projection', 'Transverse_Mercator')]

        for key, value in incremental_additions:
            self.validate_as['layers'][0][key] = value
            self.assertNoError()

    def test_fields_exist(self):
        updates = {'layers': [{'name': 'harv_samp_cur'}],
                   'value': TEST_DATA + '/carbon/input/harv_samp_cur.shp',
                   'fieldsExist': ['Start_date', 'Cut_cur', 'BCEF_cur']}
        self.validate_as.update(updates)
        self.assertNoError()

        self.validate_as['fieldsExist'].append('nonexistent_field')
        self.assertError()

class DBFCheckerTester(CheckerTester):
        def setUp(self):
            self.validate_as = {'type': 'DBF',
                                'value': TEST_DATA +
                                '/carbon/input/carbon_pools_samp.dbf',
                                'fieldsExist': []}
            self.checker = iui_validator.DBFChecker()

        def test_fields_exist(self):
            self.validate_as['fieldsExist'] = ['C_above', 'LULC', 'C_soil']
            self.assertNoError()

        def test_nonexistent_fields(self):
            self.validate_as['fieldsExist'].append('nonexistent_field')
            self.assertError()

        def test_restrictions(self):
            regexp_int = {'pattern': '[0-9]*'}
            date_regexp = {'pattern': '[0-9]{4}|0'}
            num_restriction = {'field': 'BCEF_cur',
                               'validateAs': {'type': 'number',
                                              'allowedValues': regexp_int}}
            const_restriction = {'field': 'BCEF_cur',
                                 'validateAs': {'type': 'number',
                                                'greaterThan': 0,
                                                'gteq': 1,
                                                'lteq': 2,
                                                'lessThan': 2}}
            field_restriction = {'field': 'C_den_cur',
                                 'validateAs': {'type': 'number',
                                                'lessThan': 'BCEF_cur'}}
            str_restriction = {'field': 'Start_date',
                               'validateAs': {'type': 'string',
                                              'allowedValues': date_regexp}}

            self.validate_as['restrictions'] = [num_restriction,
                                                const_restriction,
                                                field_restriction,
                                                str_restriction]
            self.assertNoError()

class PrimitiveCheckerTester(CheckerTester):
    def setUp(self):
        self.validate_as = {'type': 'string',
                            'allowedValues': {'pattern': '[a-z]+'}}
        self.checker = iui_validator.PrimitiveChecker()

    def test_value(self):
        self.validate_as['value'] = 'aaaabasd'
        self.assertNoError()

    def test_value_not_allowed(self):
        self.validate_as['value'] = '12341aasd'
        self.assertError()

    def test_ignore_case_flag(self):
        self.validate_as['value'] = 'AsdAdnS'
        self.validate_as['allowedValues']['flag'] = 'ignoreCase'
        self.assertNoError()

    def test_dot_all_flag(self):
        self.validate_as['value'] = 'asda\n'
        self.validate_as['allowedValues']['flag'] = 'dotAll'
        self.validate_as['allowedValues']['pattern'] = '[a-z]+.+'
        self.assertNoError()

class NumberCheckerTester(CheckerTester):
    def setUp(self):
        self.validate_as = {'type':'number',
                            'value': 5}
        self.checker = iui_validator.NumberChecker()

    def test_gt(self):
        self.validate_as['greaterThan'] = 2
        self.assertNoError()

    def test_lt(self):
        self.validate_as['lessThan'] = 7
        self.assertError()

    def test_gteq(self):
        self.validate_as['gteq'] = 5
        self.assertNoError()

    def test_lteq(self):
        self.validate_as['lteq'] = 5
        self.assertNoError()

    def test_all(self):
        self.validate_as['lteq'] = 5
        self.validate_as['lessThan'] = 6
        self.validate_as['gteq'] = 5
        self.validate_as['greaterThan'] = 4
        self.assertNoError()
