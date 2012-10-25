"""Module for the execution of the biophysical component of the InVEST Nutrient
Retention model."""

import re
import logging
import os
import sys

from osgeo import gdal
from osgeo import ogr

from invest_natcap import raster_utils
from invest_natcap.nutrient import nutrient_core
from invest_natcap.invest_core import fileio as fileio

LOGGER = logging.getLogger('nutrient_biophysical')
logging.basicConfig(format='%(asctime)s %(name)-15s %(levelname)-8s \
    %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

def execute(args):
    """File opening layer for the InVEST nutrient retention model.

        args - a python dictionary with the following entries:
            'workspace_dir' - a string uri pointing to the current workspace.
            'dem_uri' - a string uri pointing to the Digital Elevation Map
                (DEM), a GDAL raster on disk.
            'pixel_yield_uri' - a string uri pointing to the water yield raster
                output from the InVEST Water Yield model.
            'landuse_uri' - a string uri pointing to the landcover GDAL raster.
            'watersheds_uri' - a string uri pointing to an OGR shapefile on
                disk representing the user's watersheds.
            'subwatersheds_uri' - a string uri pointing to an OGR shapefile on
                disk representing the user's subwatersheds.
            'bio_table_uri' - a string uri to a supported table on disk
                containing nutrient retention values.
            'threshold_uri' - a string uri to a supported table on disk
                containing water purification details.
            'nutrient_type' - a string, either 'nitrogen' or 'phosphorus'
            'accum_threshold' - a number representing the flow accumulation.

        returns nothing.
    """
    print args

    workspace = args['workspace_dir']
    output_dir = os.path.join(workspace, 'output')
    service_dir = os.path.join(workspace, 'service')
    intermediate_dir = os.path.join(workspace, 'intermediate')

    for folder in [workspace, output_dir, service_dir, intermediate_dir]:
        try:
            os.makedirs(folder)
        except OSError:
            # Thrown when folder already exists
            pass

    biophysical_args = {}

    # Open rasters provided in the args dictionary.
    LOGGER.info('Opening user-defined rasters')
    raster_list = ['dem_uri', 'pixel_yield_uri', 'landuse_uri']
    for raster_key in raster_list:
        new_key = re.sub('_uri$', '', raster_key)
        LOGGER.debug('Opening "%s" raster at %s', new_key, str(args[raster_key]))
        biophysical_args[new_key] = gdal.Open(str(args[raster_key]))

    # Open shapefiles provided in the args dictionary
    LOGGER.info('Opening user-defined shapefiles')
    encoding = sys.getfilesystemencoding()
    ogr_driver = ogr.GetDriverByName('ESRI Shapefile')
    shapefile_list = ['watersheds_uri', 'subwatersheds_uri']
    for shape_key in shapefile_list:
        new_key = re.sub('_uri$', '', shape_key)
        LOGGER.debug('Opening "%s" shapefile at %s', new_key, str(args[shape_key]))

        sample_shape = ogr.Open(args[shape_key].encode(encoding), 1)
        copy_uri = os.path.join(output_dir, new_key + '.shp')
        copy = ogr_driver.CopyDataSource(sample_shape, copy_uri)
        LOGGER.debug('Saving shapefile copy to %s', copy_uri)

        biophysical_args[new_key] = copy

    LOGGER.info('Opening tables')
    biophysical_args['bio_table'] = fileio.TableHandler(args['bio_table_uri'])
    biophysical_args['threshold_table'] =\
        fileio.TableHandler(args['threshold_table_uri'])

    LOGGER.info('Copying other values for internal use')
    biophysical_args['nutrient_type'] = args['nutrient_type']
    biophysical_args['accum_threshold'] = args['accum_threshold']

