# Some tracer code to see how urlllib and gdal work together

from urllib import urlopen
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

def open(datatype_dict):
    if datatype_dict['type'] == 'gdal':
        return gdal_open(datatype_dict['uri'])
    if datatype_dict['type'] == 'dbf':
        return dbf_open(datatype_dict['uri'])

def gdal_open(filename):
    gdal.AllRegister()
    raster = gdal.Open(filename, GA_ReadOnly)
    if raster is None:
        raise Exception, 'Could not open image'
    return raster

def dbf_open(filename):
    return dbf.Dbf(filename, True)
