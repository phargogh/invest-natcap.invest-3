import logging
import tempfile

import numpy
cimport numpy
import osgeo
from osgeo import gdal

from invest_natcap.routing import routing_utils
from invest_natcap import raster_utils
import routing_cython_core

from libcpp.stack cimport stack
from libcpp.queue cimport queue
from libc.math cimport atan
from libc.math cimport tan
from libc.math cimport sqrt

logging.basicConfig(format='%(asctime)s %(name)-18s %(levelname)-8s \
    %(message)s', lnevel=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

LOGGER = logging.getLogger('monthly water yield cython core')

def calculate_tp(dem_uri, precip_uri, dt_uri, tp_out_uri):
    """Function to calculate the sum of the direct flows onto a pixel
        plus the precipitation on that pixel.

        dem_uri - a URI to a GDAL dataset representing the DEM.
        precip_uri - a URI to a GDAL dataset representing the DEM.
        dt_uri - a URI to a GDAL dataset representing the direct flow
        tp_out_uri - a URI to an output GDAL dataset that represents the total
            flow on to a pixel plus the precipitation on that pixel.

        returns nothing"""
        
    cdef int current_row, current_col, neighbor_row, neighbor_col, neighbor_direction
    cdef int n_cols, n_rows

    #Diagonal offsets are based off the following index notation for neighbors
    #    3 2 1
    #    4 p 0
    #    5 6 7

    cdef int *row_offsets = [0, -1, -1, -1,  0,  1, 1, 1]
    cdef int *col_offsets = [1,  1,  0, -1, -1, -1, 0, 1]

    cdef int *inflow_offsets = [4, 5, 6, 7, 0, 1, 2, 3]

    cdef float tp_current, precip_nodata, dt_current, outflow_weight
    cdef float tp_nodata = -1.0

    #Align the input rasters so all the arrays align in the following loop
    dem_aligned_uri = raster_utils.temporary_filename()
    precip_aligned_uri = raster_utils.temporary_filename()
    dt_aligned_uri = raster_utils.temporary_filename()
    out_pixel_size = raster_utils.get_cell_size_from_uri(dem_uri)
    raster_utils.align_dataset_list(
        [dem_uri, precip_uri, dt_uri],
        [dem_aligned_uri, precip_aligned_uri, dt_aligned_uri], ['nearest'] * 3,
        out_pixel_size, 'intersection', 0)

    flow_direction_uri = raster_utils.temporary_filename()
    routing_utils.flow_direction_inf(dem_aligned_uri, flow_direction_uri)

    outflow_direction_uri = raster_utils.temporary_filename()
    outflow_weights_uri = raster_utils.temporary_filename()
    routing_cython_core.calculate_flow_graph(
        flow_direction_uri, outflow_weights_uri, outflow_direction_uri,
        dem_aligned_uri)

    outflow_direction_dataset = gdal.Open(outflow_direction_uri)
    cdef float outflow_direction_nodata = raster_utils.get_nodata_from_uri(
        outflow_direction_uri)
    n_cols = outflow_direction_dataset.RasterXSize
    n_rows = outflow_direction_dataset.RasterYSize

    outflow_direction_file = tempfile.TemporaryFile()
    cdef numpy.ndarray[numpy.npy_byte, ndim=2] outflow_direction_array = (
        raster_utils.load_memory_mapped_array(
            outflow_direction_uri, outflow_direction_file))

    outflow_weights_file = tempfile.TemporaryFile()
    cdef numpy.ndarray[numpy.npy_float32, ndim=2] outflow_weights_array = (
        raster_utils.load_memory_mapped_array(
            outflow_weights_uri, outflow_weights_file))

    dt_file = tempfile.TemporaryFile()
    cdef numpy.ndarray[numpy.npy_float32, ndim=2] dt_array = (
        raster_utils.load_memory_mapped_array(
            dt_aligned_uri, dt_file))
    cdef float dt_nodata = raster_utils.get_nodata_from_uri(dt_aligned_uri)

    precip_file = tempfile.TemporaryFile()
    cdef numpy.ndarray[numpy.npy_float32, ndim=2] precip_array = (
        raster_utils.load_memory_mapped_array(
            precip_aligned_uri, precip_file))
    precip_nodata = raster_utils.get_nodata_from_uri(precip_aligned_uri)


    tp_data_file = tempfile.TemporaryFile()

    cdef numpy.ndarray[numpy.npy_float32, ndim=2] tp_array = (
        numpy.memmap(tp_data_file, dtype=numpy.float32, mode='w+',
                     shape=(n_rows, n_cols)))
    tp_array[:] = tp_nodata

    for current_row in range(1, n_rows-1):
        for current_col in range(1, n_cols-1):
            tp_current = precip_array[current_row, current_col]
            if tp_current == precip_nodata:
                tp_current = 0.0
            for direction_index in range(8):
                neighbor_row = current_row + row_offsets[direction_index]
                neighbor_col = current_col + col_offsets[direction_index]

                neighbor_direction = (
                    outflow_direction_array[neighbor_row, neighbor_col])
                if neighbor_direction == outflow_direction_nodata:
                    continue
                if (inflow_offsets[direction_index] != neighbor_direction and 
                    inflow_offsets[direction_index] != (neighbor_direction - 1) % 8):
                    #then neighbor doesn't inflow into current cell
                    continue

                dt_current = dt_array[neighbor_row, neighbor_col]
                if dt_current == dt_nodata:
                    continue

                outflow_weight = (
                    outflow_weights_array[neighbor_row, neighbor_col])
                if (inflow_offsets[direction_index] == 
                    (neighbor_direction - 1) % 8):
                    outflow_weight = 1.0 - outflow_weight

                tp_current += dt_current * outflow_weight

            tp_array[current_row, current_col] = tp_current

    raster_utils.new_raster_from_base_uri(
        dem_aligned_uri, tp_out_uri, 'GTiff', tp_nodata,
        gdal.GDT_Float32)

    tp_dataset = gdal.Open(tp_out_uri, gdal.GA_Update)
    tp_band = tp_dataset.GetRasterBand(1)
    tp_band.WriteArray(tp_array)
