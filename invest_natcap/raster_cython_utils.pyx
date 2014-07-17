import os
import tempfile
import logging
import time

cimport numpy
import numpy
cimport cython
from libcpp.map cimport map

from osgeo import gdal

logging.basicConfig(format='%(asctime)s %(name)-18s %(levelname)-8s \
    %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

LOGGER = logging.getLogger('raster_cython_utils')


@cython.boundscheck(False)
def reclassify_by_dictionary(dataset, rules, output_uri, format,
    float default_value, datatype, output_dataset):
    """Convert all the non-default values in dataset to the values mapped to
        by rules.  If there is no rule for an input value it is replaced by
        the default output value (which may or may not be the raster's nodata
        value ... it could just be any default value).

        dataset - GDAL raster dataset
        rules - a dictionary of the form:
            {'dataset_value1' : 'output_value1', ...
             'dataset_valuen' : 'output_valuen'}
             used to map dataset input types to output
        output_uri - The location to hold the output raster on disk
        format - either 'MEM' or 'GTiff'
        default_value - output raster dataset default value (may be nodata)
        datatype - a GDAL output type

        return the mapped raster as a GDAL dataset"""

    dataset_band = dataset.GetRasterBand(1)

    cdef map[float,float] lookup
    for key in rules.keys():
        lookup[float(key)] = rules[key]

    output_band = output_dataset.GetRasterBand(1)
    
    cdef int n_rows = output_band.YSize
    cdef int n_cols = output_band.XSize
    cdef numpy.ndarray[numpy.float_t, ndim=2] dataset_array = numpy.empty((1, n_cols))
    cdef float value = 0.0

    for row in range(n_rows):
        dataset_band.ReadAsArray(0,row,output_band.XSize,1, buf_obj = dataset_array)
        for col in range(n_cols):
            value = dataset_array[0,col]
            if lookup.count(value) == 1:
                dataset_array[0,col] = lookup[value]
            else:
                dataset_array[0,col] = default_value
        output_band.WriteArray(dataset_array, 0, row)
        
    output_band = None
    output_dataset.FlushCache()
    
    return output_dataset


def _cython_calculate_slope(dem_dataset_uri, slope_uri):
    """Generates raster maps of slope.  Follows the algorithm described here:
        http://webhelp.esri.com/arcgiSDEsktop/9.3/index.cfm?TopicName=How%20Slope%20works 
        and generates a slope dataset as a percent
        
        dem_dataset_uri - (input) a URI to a  single band raster of z values.
        slope_uri - (input) a path to the output slope uri in percent.

        returns nothing"""

    #Read the DEM directly into an array
    cdef float a,b,c,d,e,f,g,h,i,dem_nodata
    cdef int row_index, col_index, n_rows, n_cols

    dem_dataset = gdal.Open(dem_dataset_uri)
    dem_band = dem_dataset.GetRasterBand(1)
    dem_nodata = dem_band.GetNoDataValue()

    slope_dataset = gdal.Open(slope_uri, gdal.GA_Update)
    slope_band = slope_dataset.GetRasterBand(1)
    slope_nodata = slope_band.GetNoDataValue()

    gt = dem_dataset.GetGeoTransform()
    cdef float cell_size_times_8 = gt[1] * 8

    n_rows = dem_band.YSize
    n_cols = dem_band.XSize

    cdef numpy.ndarray[numpy.float_t, ndim=2] dem_array = numpy.empty((3, n_cols))
    cdef numpy.ndarray[numpy.float_t, ndim=2] slope_array = numpy.empty((1, n_cols))

    #Fill the top and bottom row of the slope since we won't touch it in this loop
    slope_array[0, :] = slope_nodata
    slope_band.WriteArray(slope_array, 0, 0)
    slope_band.WriteArray(slope_array, 0, n_rows - 1)
    
    cdef numpy.ndarray[numpy.float_t, ndim=2] dzdx = numpy.empty((1, n_cols))
    cdef numpy.ndarray[numpy.float_t, ndim=2] dzdy = numpy.empty((1, n_cols))
    
    for row_index in xrange(1, n_rows - 1):
        #Loop through the dataset 3 rows at a time
        dem_array = dem_band.ReadAsArray(0, row_index - 1, n_cols, 3, buf_obj=dem_array)
        slope_array[0, :] = slope_nodata
        dzdx[:] = slope_nodata
        dzdy[:] = slope_nodata
        for col_index in xrange(1, n_cols - 1):
            # abc
            # def
            # ghi

            a = dem_array[0, col_index - 1]
            if a == dem_nodata: continue
            b = dem_array[0, col_index]
            if b == dem_nodata: continue
            c = dem_array[0, col_index + 1]
            if c == dem_nodata: continue
            d = dem_array[1, col_index - 1]
            if d == dem_nodata: continue
            e = dem_array[1, col_index]
            if e == dem_nodata: continue
            f = dem_array[1, col_index + 1]
            if f == dem_nodata: continue
            g = dem_array[2, col_index - 1]
            if g == dem_nodata: continue
            h = dem_array[2, col_index]
            if h == dem_nodata: continue
            i = dem_array[2, col_index + 1]
            if i == dem_nodata: continue

            dzdx[0, col_index] = ((c+2*f+i) - (a+2*d+g)) / (cell_size_times_8)
            dzdy[0, col_index] = ((g+2*h+i) - (a+2*b+c)) / (cell_size_times_8)
            #output in terms of percent
        
        slope_array[:] = numpy.where(dzdx != slope_nodata, numpy.tan(numpy.arctan(numpy.sqrt(dzdx**2 + dzdy**2))) * 100, slope_nodata)
        slope_band.WriteArray(slope_array, 0, row_index)

cdef long long _f(long long x, long long i, long long gi):
    return (x-i)*(x-i)+ gi*gi

@cython.cdivision(True)
cdef long long _sep(long long i, long long u, long long gu, long long gi):
    return (u*u - i*i + gu*gu - gi*gi) / (2*(u-i))
        
        
@cython.boundscheck(False)
def _distance_transform_edt(input_mask_uri, output_distance_uri):
    """Calculate the Euclidean distance transform on input_mask_uri and output
        the result into an output raster

        input_mask_uri - a gdal raster to calculate distance from the 0 value
            pixels

        output_distance_uri - will make a float raster w/ same dimensions and
            projection as input_mask_uri where all non-zero values of
            input_mask_uri are equal to the euclidean distance to the closest
            0 pixel.

        returns nothing"""

    input_mask_ds = gdal.Open(input_mask_uri)
    input_mask_band = input_mask_ds.GetRasterBand(1)
    cdef int n_cols = input_mask_ds.RasterXSize
    cdef int n_rows = input_mask_ds.RasterYSize

    cdef int input_nodata = input_mask_band.GetNoDataValue()

    #create a transposed g function
    file_handle, g_dataset_uri = tempfile.mkstemp()
    os.close(file_handle)
    cdef int g_nodata = -1
    
    input_projection = input_mask_ds.GetProjection()
    input_geotransform = input_mask_ds.GetGeoTransform()
    driver = gdal.GetDriverByName('GTiff')
    #invert the rows and columns since it's a transpose
    g_dataset = driver.Create(
        g_dataset_uri.encode('utf-8'), n_cols, n_rows, 1, gdal.GDT_Int32,
        options=['TILED=YES', 'BLOCKXSIZE=%d' % 16, 'BLOCKYSIZE=%d' % 16])
        
    g_dataset.SetProjection(input_projection)
    g_dataset.SetGeoTransform(input_geotransform)
    g_band = g_dataset.GetRasterBand(1)
    g_band.SetNoDataValue(g_nodata)
    
    cdef float output_nodata = -1.0
    output_dataset = driver.Create(
        output_distance_uri.encode('utf-8'), n_cols, n_rows, 1, 
        gdal.GDT_Float64, options=['TILED=YES', 'BLOCKXSIZE=%d' % 16, 'BLOCKYSIZE=%d' % 16])
    output_dataset.SetProjection(input_projection)
    output_dataset.SetGeoTransform(input_geotransform)
    output_band = output_dataset.GetRasterBand(1)
    output_band.SetNoDataValue(output_nodata)
    
    cdef int numerical_inf = n_cols + n_rows

    LOGGER.info('Distance Transform Phase 1')
    #phase one, calculate column G(x,y)
    
    cdef numpy.ndarray[numpy.int32_t, ndim=2] g_array = (
        numpy.empty((n_rows, 1), dtype=numpy.int32))
    cdef numpy.ndarray[numpy.uint8_t, ndim=2] b_array
    
    cdef int col_index, row_index, q_index, u_index
    cdef long long w
    for col_index in xrange(n_cols):
        b_array = input_mask_band.ReadAsArray(
            xoff=col_index, yoff=0, win_xsize=1, win_ysize=n_rows)
        
        #named _transposed so we remember column is flipped to row
        if b_array[0, 0] and b_array[0, 0] != input_nodata:
            g_array[0, 0] = 0
        else:
            g_array[0, 0] = numerical_inf

        #pass 1 go down
        for row_index in xrange(1, n_rows):
            if b_array[row_index, 0] and b_array[row_index, 0] != input_nodata:
                g_array[row_index, 0] = 0
            else:
                g_array[row_index, 0] = (
                    1 + g_array[row_index - 1, 0])

        #pass 2 come back up
        for row_index in xrange(n_rows-2, -1, -1):
            if (g_array[row_index + 1, 0] <
                g_array[row_index, 0]):
                g_array[row_index, 0] = (
                    1 + g_array[row_index + 1, 0])
        g_band.WriteArray(
            g_array, xoff=col_index, yoff=0)

    g_band.FlushCache()
    LOGGER.info('Distance Transform Phase 2')
    cdef numpy.ndarray[numpy.int64_t, ndim=1] s_array = numpy.zeros(
        n_cols, dtype=numpy.int64)
    cdef numpy.ndarray[numpy.int64_t, ndim=1] t_array = numpy.zeros(
        n_cols, dtype=numpy.int64)
    cdef numpy.ndarray[numpy.float64_t, ndim=2] dt = numpy.empty(
        (1, n_cols), dtype=numpy.float64)
    
    for row_index in xrange(n_rows):
        g_array = g_band.ReadAsArray(
            xoff=0, yoff=row_index, win_xsize=n_cols, win_ysize=1)
        
        q_index = 0
        s_array[0] = 0
        t_array[0] = 0
        for u_index in xrange(1, n_cols):
            while (q_index >= 0 and
                _f(t_array[q_index], s_array[q_index], 
                    g_array[0, s_array[q_index]]) >
                _f(t_array[q_index], u_index, g_array[0, u_index])):
                q_index -= 1
            if q_index < 0:
               q_index = 0
               s_array[0] = u_index
            else:
                w = 1 + _sep(
                    s_array[q_index], u_index, g_array[0, u_index],
                    g_array[0, s_array[q_index]])
                if w < n_cols:
                    q_index += 1
                    s_array[q_index] = u_index
                    t_array[q_index] = w

        for u_index in xrange(n_cols-1, -1, -1):
            dt[0, u_index] = _f(
                u_index, s_array[q_index],
                g_array[0, s_array[q_index]])
            if u_index == t_array[q_index]:
                q_index -= 1
        
        b_array = input_mask_band.ReadAsArray(
            xoff=0, yoff=row_index, win_xsize=n_cols, win_ysize=1)
        
        dt = numpy.sqrt(dt)
        dt[b_array == input_nodata] = output_nodata
        output_band.WriteArray(dt, xoff=0, yoff=row_index)

    gdal.Dataset.__swig_destroy__(g_dataset)
    try:
        os.remove(g_dataset_uri)
    except OSError:
        LOGGER.warn("couldn't remove file %s" % g_dataset_uri)
        
        
def new_raster_from_base_uri(base_uri, *args, **kwargs):
    """A wrapper for the function new_raster_from_base that opens up
        the base_uri before passing it to new_raster_from_base.

        base_uri - a URI to a GDAL dataset on disk.

        All other arguments to new_raster_from_base are passed in.

        Returns nothing.
        """
    base_raster = gdal.Open(base_uri)
    new_raster = new_raster_from_base(base_raster, *args, **kwargs)
    gdal.Dataset.__swig_destroy__(new_raster)
    gdal.Dataset.__swig_destroy__(base_raster)
    new_raster = None
    base_raster = None


def new_raster_from_base(
    base, output_uri, gdal_format, nodata, datatype, fill_value=None,
    n_rows=None, n_cols=None, dataset_options=[]):
    """Create a new, empty GDAL raster dataset with the spatial references,
        geotranforms of the base GDAL raster dataset.

        base - a the GDAL raster dataset to base output size, and transforms on
        output_uri - a string URI to the new output raster dataset.
        gdal_format - a string representing the GDAL file format of the
            output raster.  See http://gdal.org/formats_list.html for a list
            of available formats.  This parameter expects the format code, such
            as 'GTiff' or 'MEM'
        nodata - a value that will be set as the nodata value for the
            output raster.  Should be the same type as 'datatype'
        datatype - the pixel datatype of the output raster, for example
            gdal.GDT_Float32.  See the following header file for supported
            pixel types:
            http://www.gdal.org/gdal_8h.html#22e22ce0a55036a96f652765793fb7a4
        fill_value - (optional) the value to fill in the raster on creation
        n_rows - (optional) if set makes the resulting raster have n_rows in it
            if not, the number of rows of the outgoing dataset are equal to
            the base.
        n_cols - (optional) similar to n_rows, but for the columns.
        dataset_options - (optional) a list of dataset options that gets
            passed to the gdal creation driver, overrides defaults

        returns a new GDAL raster dataset."""

    if n_rows is None:
        n_rows = base.RasterYSize
    if n_cols is None:
        n_cols = base.RasterXSize
    projection = base.GetProjection()
    geotransform = base.GetGeoTransform()
    driver = gdal.GetDriverByName(gdal_format)
    
    base_band = base.GetRasterBand(1)
    block_size = base_band.GetBlockSize()
    
    if dataset_options == []:
        dataset_options = [
            'BIGTIFF=IF_SAFER', 'BLOCKXSIZE=%d' % block_size[0],
            'BLOCKYSIZE=%d' % block_size[1]]
    LOGGER.info('dataset_options=%s' % str(dataset_options))
    new_raster = driver.Create(
        output_uri.encode('utf-8'), n_cols, n_rows, 1, datatype,
        options=dataset_options)
    base_band = None
    new_raster.SetProjection(projection)
    new_raster.SetGeoTransform(geotransform)
    band = new_raster.GetRasterBand(1)

    band.SetNoDataValue(nodata)
    if fill_value != None:
        band.Fill(fill_value)
    else:
        band.Fill(nodata)
    band = None

    return new_raster

    
def convolve_2d(weight_uri, kernel_type, max_distance_in, output_uri):
    """Does a direct convolution on a predefined kernel 
    
        
        each output pixel at ij gets the value:
            sum_xy(weight_uri_xy * decay_xy_ij)
            
            
        define d(xy, ij) as the Euclidan distance between coordinates xy and ij
        then, decay_xy_ij is
            
            1 - d(xy, ij)/max_distance for 'linear'
            exp(-(2.99/max_distance)*d(xy,ij)) for 'exponential'

            if d(xy, ij) < max_distance, else 0.0
            
        weight_uri - this is the source raster
        kernel_type - 'linear' or 'exponential'
        max_distance - defined in equation above (units are pixel size)
        output_uri - the raster output of same size and projection of
            weight_uri
            
        returns nothing"""
        
    weight_ds = gdal.Open(weight_uri)
    weight_band = weight_ds.GetRasterBand(1)
    weight_array = weight_band.ReadAsArray()
    new_raster_from_base_uri(
        weight_uri, output_uri, 'GTiff', -1, gdal.GDT_Float32)
    
    cdef int n_rows, n_cols, row_index, col_index
    cdef int weight_left_index, weight_right_index
    cdef int kernel_left_index, kernel_right_index
    cdef int max_distance = max_distance_in
    
    n_rows, n_cols = weight_array.shape
    
    output_ds = gdal.Open(output_uri, gdal.GA_Update)
    output_band = output_ds.GetRasterBand(1)
    output_array = output_band.ReadAsArray()
    
    #build a kernel
    kernel_size = max_distance * 2 + 1
    kernel = numpy.empty((kernel_size, kernel_size))
    
    def distance(row_index, col_index):
        """closure for an euclidan distance calc"""
        dist = numpy.sqrt(
            (row_index - kernel_size - 1) ** 2 +
            (col_index - kernel_size - 1) ** 2)
        if dist > max_distance_in:
            return 0.0
        if kernel_type == 'linear':
            return 1 - dist/max_distance_in
        elif kernel_type == 'exponential':
            return  numpy.exp(-(2.99/max_distance_in) * dist)
    
    for row_index in xrange(kernel_size):
        for col_index in xrange(kernel_size):
            kernel[row_index, col_index] = distance(row_index, col_index)
    
    last_time = time.time()
    for row_index in xrange(n_rows):
        current_time = time.time()
        if current_time - last_time > 5.0:
            LOGGER.info('convolve 2d %.2f%% complete' % ((row_index * n_cols) / float(n_rows * n_cols) * 100.0))
            last_time = current_time
        for col_index in xrange(n_cols):
            
            #snip the window of the kernel over the window of the weight
            if col_index >= max_distance:
                weight_left_index = col_index - max_distance
                kernel_left_index = 0
            else:
                weight_left_index = 0
                kernel_left_index = max_distance - col_index
            
            if col_index < n_cols - max_distance - 1:
                weight_right_index = col_index + max_distance + 1
                kernel_right_index = kernel_size
            else:
                weight_right_index = n_cols
                kernel_right_index = max_distance + (n_cols - col_index)
                
            #snip the window of the kernel over the window of the weight
            if row_index >= max_distance:
                weight_top_index = row_index - max_distance
                kernel_top_index = 0
            else:
                weight_top_index = 0
                kernel_top_index = max_distance - row_index
            
            if row_index < n_rows - kernel_size / 2:
                weight_bottom_index = row_index + kernel_size / 2 + 1
                kernel_bottom_index = kernel_size
            else:
                weight_bottom_index = n_rows
                kernel_bottom_index = max_distance + (n_rows - row_index)
            
            try:
                output_array[row_index, col_index] = numpy.sum(
                    kernel[kernel_top_index:kernel_bottom_index,
                        kernel_left_index:kernel_right_index] * 
                    weight_array[weight_top_index:weight_bottom_index,
                        weight_left_index:weight_right_index])
            except ValueError as e:
                print row_index
                print col_index
                print kernel_top_index
                print kernel_bottom_index
                print kernel_left_index
                print kernel_right_index
                print weight_top_index
                print weight_bottom_index
                print weight_left_index
                print weight_right_index
                print weight_array.shape
                print kernel.shape
                raise e
    
    LOGGER.info('convolve 2d 100% complete')
    output_band = output_ds.GetRasterBand(1)
    output_band.WriteArray(output_array)        
    