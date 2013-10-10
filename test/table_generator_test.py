"""Unit Tests For Table Generator Module"""

import os, sys
from osgeo import gdal
from osgeo import ogr
import unittest
from nose.plugins.skip import SkipTest
import invest_natcap.testing

from invest_natcap import table_generator
import invest_test_core

class TestTableGenerator(unittest.TestCase):
    def test_get_column_headers(self):
        """Unit test for getting the column headers from a dictionary"""
        #raise SkipTest
        sample_dict = {
                'col_1' : {'id': 0},
                'col_2' : {'id': 2},
                'col_3' : {'id': 1}}

        expected_result = ['col_1', 'col_3', 'col_2']

        col_headers = table_generator.get_column_headers(sample_dict)

        self.assertEqual(expected_result, col_headers)
    
    def test_get_column_headers_robust(self):
        """Unit test for getting the column headers from a more complicated
            dictionary setup"""
        #raise SkipTest
        sample_dict = {
                'date' : {'id': 1, 'time':'day'},
                'price' : {'id': 6, 'price':'expensive'},
                'product' : {'id': 0, 'product':'chips'},
                'comments' : {'id': 2, 'comment':'bad product'}}

        expected_result = ['product', 'date', 'comments', 'price']

        col_headers = table_generator.get_column_headers(sample_dict)

        self.assertEqual(expected_result, col_headers)
    
    def test_get_row_data(self):
        """Unit test for getting the row data from a dictionary"""
        #raise SkipTest
        sample_dict = {
                    0: {'col_1':'value_1', 'col_2':'value_4'},
                    1: {'col_1':'value_2', 'col_2':'value_5'},
                    2: {'col_1':'value_3', 'col_2':'value_6'}}

        col_headers = ['col_1', 'col_2']

        expected_result = [
                ['value_1', 'value_4'],
                ['value_2', 'value_5'],
                ['value_3', 'value_6']]

        row_data = table_generator.get_row_data(sample_dict, col_headers)

        self.assertEqual(expected_result, row_data)
    
    def test_get_row_data_robust(self):
        """Unit test for getting the row data from a more complicated
            dictionary"""
        #raise SkipTest
        sample_dict = {
                3: {'date':'09-13', 'price':.54, 'product':'chips'},
                0: {'date':'08-14', 'price':23.4, 'product':'mustard'},
                1: {'date':'04-13', 'price':100, 'product':'hats'},
                2: {'date':'06-12', 'price':56.50, 'product':'gloves'}}

        col_headers = ['product', 'price', 'date']

        expected_result = [
                ['mustard', 23.4, '08-14'],
                ['hats', 100, '04-13'],
                ['gloves', 56.50, '06-12'],
                ['chips', .54, '09-13']]

        row_data = table_generator.get_row_data(sample_dict, col_headers)

        self.assertEqual(expected_result, row_data)

    def test_generate_table(self):
        """Unit test for creating a table from a dictionary as a string
            representing html"""
        raise SkipTest
        sample_dict = {
                'cols':{
                    'date' : {'id': 1, 'time':'day'},
                    'price' : {'id': 6, 'price':'expensive'},
                    'product' : {'id': 0, 'product':'chips'}},
                'rows':{
                    0: {'date':'9/13', 'price':'expensive', 'product':'chips'},
                    1: {'date':'3/13', 'price':'cheap', 'product':'peanuts'},
                    2: {'date':'5/12', 'price':'moderate', 'product':'mints'}}
                }
        expected_result = ['product', 'date', 'comments', 'price']

        col_headers = table_generator.get_column_headers(sample_dict)

        self.assertEqual(expected_result, col_headers)
