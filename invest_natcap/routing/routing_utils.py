"""This file contains functions to simulate overland flow on GIS rasters
    defined by DEM raster datasets.  Here are some conventions of this model:

    A single pixel defines its neighbors as follows:

    3 2 1
    4 p 0
    5 6 7

    The 'p' refers to 'pixel' since the flow model is pixel centric.

    One of the outputs from this model will be a flow graph represented as a
    sparse matrix.  The rows in the matrix are the originating nodes and the
    columns represent the outflow, thus G[i,j]'s value is the fraction of flow
    from node 'i' to node 'j'.  The following expresses how to calculate the
    matrix indexes from the pixels original row,column position in the raster.
    Given that the raster's dimension is 'n_rows' by 'n_columns', pixel located
    at row 'r' and colunn 'c' has index

        (r,c) -> r * n_columns + c = index

    Likewise given 'index' r and c can be derived as:

        (index) -> (index div n_columns, index mod n_columns) where 'div' is
            the integer division operator and 'mod' is the integer remainder
            operation."""

import os
import logging
import collections
import time
import tempfile
import shutil

from osgeo import gdal
import osgeo.gdalconst
import numpy

from invest_natcap import raster_utils
import invest_cython_core
import routing_cython_core

logging.basicConfig(format='%(asctime)s %(name)-18s %(levelname)-8s \
    %(message)s', lnevel=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

LOGGER = logging.getLogger('routing')

def route_flux(
    dem_uri, source_uri, absorption_rate_uri, loss_uri, flux_uri,
    workspace_dir, aoi_uri=None):

    """This function will route flux across a landscape given a dem to
        guide flow from a d-infinty flow algorithm, and a custom function
        that will operate on input flux and other user defined arguments
        to determine nodal output flux.

        dem_uri - a URI to a DEM raster
        source_uri - a GDAL dataset that has source flux per pixel
        absorption_rate_uri - a GDAL floating point dataset that has a percent
            of flux absorbed per pixel
        loss_uri - an output URI to to the dataset that will output the
            amount of flux absorbed by each pixel
        flux_uri - a URI to an output dataset that records the amount of flux
            traveling through each pixel
        workspace_dir - a URI to an existing directory that can be used to
            write intermediate files to
        aoi_uri - an OGR datasource for an area of interest polygon.
            the routing flux calculation will only occur on those pixels
            and neighboring pixels will either be raw outlets or
            non-contibuting inputs depending on the orientation of the DEM.

        returns nothing"""

    flow_direction_uri = os.path.join(workspace_dir, 'flow_direction.tif')
    outflow_weights_uri = os.path.join(workspace_dir, 'outflow_weights.tif')
    outflow_direction_uri = os.path.join(
        workspace_dir, 'outflow_directions.tif')
    routing_cython_core.calculate_flow_direction(dem_uri, flow_direction_uri)
    sink_cell_set, _ = routing_cython_core.calculate_flow_graph(
        flow_direction_uri, outflow_weights_uri, outflow_direction_uri)
    routing_cython_core.calculate_transport(
        outflow_direction_uri, outflow_weights_uri, sink_cell_set,
        source_uri, absorption_rate_uri, loss_uri, flux_uri)

def flow_accumulation(dem_uri, flux_output_uri):
    """A helper function to calculate flow accumulation, also returns
        intermediate rasters for future calculation.

        dem_uri - a uri to a gdal dataset representing a DEM
        flux_output_uri - location to dump the raster represetning flow
            accumulation"""

    constant_flux_source_file = tempfile.NamedTemporaryFile()
    zero_absorption_source_file = tempfile.NamedTemporaryFile()
    loss_file = tempfile.NamedTemporaryFile()

    make_constant_raster_from_base(dem_uri, 1.0, constant_flux_source_file.name)
    make_constant_raster_from_base(dem_uri, 0.0, zero_absorption_source_file.name)

    workspace_dir = tempfile.mkdtemp()

    route_flux(
        dem_uri, constant_flux_source_file.name,
        zero_absorption_source_file.name, loss_file.name, flux_output_uri,
        workspace_dir)

    shutil.rmtree(workspace_dir)


def make_constant_raster_from_base(base_dataset_uri, constant_value, out_uri):
    """A helper function that creates a new gdal raster from base, and fills
        it with the constant value provided.

        base_dataset_uri - the gdal base raster
        constant_value - the value to set the new base raster to
        out_uri - the uri of the output raster

        returns nothing"""

    base_dataset = gdal.Open(base_dataset_uri)
    out_dataset = raster_utils.new_raster_from_base(
        base_dataset, out_uri, 'GTiff', constant_value - 1,
        gdal.GDT_Float32)
    out_band, _ = raster_utils.extract_band_and_nodata(out_dataset)
    out_band.Fill(constant_value)


def stream_threshold(flow_accumulation_uri, flow_threshold, stream_uri):
    """Creates a raster of accumulated flow to each cell.
    
        flow_accumulation_data - (input) A flow accumulation dataset of type
            floating point
        flow_threshold - (input) a number indicating the threshold to declare
            a pixel a stream or no
        stream_uri - (input) the uri of the output stream dataset
        
        returns nothing"""

    flow_accumulation_dataset = gdal.Open(flow_accumulation_uri)
    stream_nodata = 255
    stream_dataset = raster_utils.new_raster_from_base(flow_accumulation_dataset, 
        stream_uri, 'GTiff', stream_nodata, gdal.GDT_Byte)
    stream_band = stream_dataset.GetRasterBand(1)
    stream_band.Fill(stream_nodata)
    stream_data_file = tempfile.TemporaryFile()
    stream_array = raster_utils.load_memory_mapped_array(
        stream_uri, stream_data_file)
    stream_array[:] = stream_nodata

    flow_accumulation_data_file = tempfile.TemporaryFile()
    flow_accumulation_array = raster_utils.load_memory_mapped_array(
        flow_accumulation_uri, flow_accumulation_data_file)
    
    flow_accumulation_band, flow_accumulation_nodata = raster_utils.extract_band_and_nodata(flow_accumulation_dataset)

    stream_array[(flow_accumulation_array != flow_accumulation_nodata) * \
                     (flow_accumulation_array >= float(flow_threshold))] = 1
    stream_array[(flow_accumulation_array != flow_accumulation_nodata) * \
                     (flow_accumulation_array < float(flow_threshold))] = 0

    stream_band.WriteArray(stream_array)


def calculate_flow_length(flow_direction_uri, flow_length_uri):
    """Calcualte the flow length of a cell given the flow direction

        flow_direction_uri - uri to a gdal dataset that represents the
            d_inf flow direction of each pixel
        flow_length_uri - the uri that the output flow length will be put to

        returns nothing"""


    flow_direction_dataset = gdal.Open(flow_direction_uri)
    _, flow_direction_nodata = raster_utils.extract_band_and_nodata(
        flow_direction_dataset)
    
    flow_length_nodata = -1.0
    flow_length_dataset = raster_utils.new_raster_from_base(
        flow_direction_dataset, flow_length_uri, 'GTiff', flow_length_nodata,
        gdal.GDT_Float32)

    def flow_length(flow_direction):
        if flow_direction == flow_direction_nodata:
            return flow_length_nodata
        return abs(numpy.sin(flow_direction)) + abs(numpy.cos(flow_direction))

    raster_utils.vectorize_rasters(
        [flow_direction_dataset], flow_length, aoi=None,
        raster_out_uri=flow_length_uri, datatype=gdal.GDT_Float32,
        nodata=flow_length_nodata)


def percent_to_sink(sink_pixels_uri, absorption_rate_uri, effect_uri):
    """This function calculates the amount of load from a single pixel
        to the source pixels given the percent absorption rate per pixel.
        
        sink_pixels_uri - the pixels of interest that will receive flux.
            This may be a set of stream pixels, or a single pixel at a
            watershed outlet.

        absorption_rate_uri - a GDAL floating point dataset that has a percent
            of flux absorbed per pixel

        effect_uri - the output GDAL dataset that shows the percent of flux
            eminating per pixel that will reach any sink pixel

        returns nothing"""

    sink_pixels_dataset = gdal.Open(sink_pixels_uri)
    absorption_rate_dataset = gdal.Open(absorption_rate_uri)

    effect_nodata = -1.0
    effect_dataset = raster_utils.new_raster_from_base(
        sink_pixels_dataset, effect_uri, 'GTiff', effect_nodata,
        gdal.GDT_Float32)

    n_cols = sink_pixels_dataset.RasterXSize
    n_rows = sink_pixels_dataset.RasterYSize

    sink_pixels_data_file = tempfile.TemporaryFile()
    sink_pixels_array = raster_utils.load_memory_mapped_array(
        sink_pixels_uri, sink_pixels_data_file)
    
    absorption_rate_data_file = tempfile.TemporaryFile()
    _, absorption_rate_nodata = raster_utils.extract_band_and_nodata(
        absorption_rate_dataset)
    absorption_rate_array = raster_utils.load_memory_mapped_array(
        absorption_rate_uri, absorption_rate_data_file)
    
    effect_band, effect_nodata = raster_utils.extract_band_and_nodata(
        effect_dataset)

    effect_data_file = tempfile.TemporaryFile()
    effect_array = numpy.memmap(effect_data_file, dtype=numpy.float32, mode='w+', shape=(n_rows, n_cols))
    effect_array[:] = effect_nodata

    for col_index in xrange(n_cols):
        for row_index in xrange(n_rows):
            if absorption_rate_array[row_index, col_index] != absorption_rate_nodata and \
                    effect_array[row_index, col_index] == effect_nodata:
                effect_array[row_index, col_index] = 1.0
                
    effect_band.WriteArray(effect_array, 0, 0)
