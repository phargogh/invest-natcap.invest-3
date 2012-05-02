"""InVEST Pollination model file handler module"""

from osgeo import gdal

import pollination_core
from invest_natcap.iui import fileio

import logging
logging.basicConfig(format='%(asctime)s %(name)-18s %(levelname)-8s \
     %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

LOGGER = logging.getLogger('pollination_biophysical')

def execute(args):
    """Open files necessary for the biophysical portion of the pollination
        model.

        args - a python dictionary with at least the following components:
        args['workspace_dir'] - a uri to the directory that will write output
            and other temporary files during calculation (required)
        args['landuse_uri'] - a uri to an input land use/land cover raster
        args['landuse_attributes_uri'] - a uri to an input CSV containing data
            on each class in the land use/land cover map (required).
        args['guilds_uri'] - a uri to an input CSV table containing data on each
            species or guild of pollinator to be modeled.
        args['ag_classes'] - a python string of space-separated integers
            representing land cover classes in the input land use/land cover
            map where each class specified is agricultural.  This string may be
            either a python string or a unicode string. (optional)

        returns nothing."""

    gdal.AllRegister()

    biophysical_args = {}
    workspace = args['workspace_dir']

    # Open the landcover raster
    biophysical_args['landuse'] = gdal.Open(str(args['landuse_uri']),
                                           gdal.GA_ReadOnly)

    # Open a Table Handler for the land use attributes table and a different
    # table handler for the Guilds table.
    att_table_handler = fileio.find_handler(args['landuse_attributes_uri'])
    guilds_handler = fileio.find_handler(args['guilds_uri'])

    # Retrieve a list of row dictionaries as a representation of the input
    # attributes table and for the input guilds table.
    biophysical_args['landuse_attributes'] = att_table_handler.get_table_list()
    biophysical_args['guilds'] = guilds_handler.get_table_list()

    # Convert agricultural classes (a space-separated list of ints) into a 
    # list of ints.  If the user has not provided a string list of ints, then
    # use an empty list instead.
    try:
        # This approach will create a list with only ints, even if the user has
        # accidentally entered additional spaces.  Any other incorrect input
        # will throw a ValueError exception.
        ag_class_list = [ int(r) for r in args['ag_classes'].split(' ') if r != '' ]
    except KeyError:
        # If the 'ag_classes' key is not present in the args dictionary, use an
        # empty list in its stead.
        ag_class_list = []

    biophysical_args['ag_classes'] = ag_class_list

    pollination_core.biophysical(biophysical_args)

