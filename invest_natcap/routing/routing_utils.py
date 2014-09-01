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

import logging
import tempfile

from osgeo import gdal
import numpy

from invest_natcap import raster_utils
import routing_cython_core

logging.basicConfig(format='%(asctime)s %(name)-18s %(levelname)-8s \
    %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

LOGGER = logging.getLogger('routing')


def route_flux(
    in_flow_direction, in_dem, in_source_uri, in_absorption_rate_uri, loss_uri,
    flux_uri, absorption_mode, aoi_uri=None, stream_uri=None):

    """This function will route flux across a landscape given a dem to
        guide flow from a d-infinty flow algorithm, and a custom function
        that will operate on input flux and other user defined arguments
        to determine nodal output flux.

        in_flow_direction - a URI to a d-infinity flow direction raster
        in_dem - a uri to the dem that generated in_flow_direction, they
            should be aligned rasters
        in_source_uri - a GDAL dataset that has source flux per pixel
        in_absorption_rate_uri - a GDAL floating point dataset that has a percent
            of flux absorbed per pixel
        loss_uri - an output URI to to the dataset that will output the
            amount of flux absorbed by each pixel
        flux_uri - a URI to an output dataset that records the amount of flux
            travelling through each pixel
        absorption_mode - either 'flux_only' or 'source_and_flux'. For
            'flux_only' the outgoing flux is (in_flux * absorption + source).
            If 'source_and_flux' then the output flux
            is (in_flux + source) * absorption.
        aoi_uri - an OGR datasource for an area of interest polygon.
            the routing flux calculation will only occur on those pixels
            and neighboring pixels will either be raw outlets or
            non-contibuting inputs depending on the orientation of the DEM.
        stream_uri - (optional) a GDAL dataset that classifies pixels as stream
            (1) or not (0).  If during routing we hit a stream pixel, all 
            upstream flux is considered to wash to zero because it will 
            reach the outlet.  The advantage here is that it can't then 
            route out of the stream

        returns nothing"""
        
    dem_uri = raster_utils.temporary_filename(suffix='.tif')
    flow_direction_uri = raster_utils.temporary_filename(suffix='.tif')
    source_uri = raster_utils.temporary_filename(suffix='.tif')
    absorption_rate_uri = raster_utils.temporary_filename(suffix='.tif')
    out_pixel_size = raster_utils.get_cell_size_from_uri(in_flow_direction)
    LOGGER.info('starting route_flux by aligning datasets')
    
    raster_utils.align_dataset_list(
        [in_flow_direction, in_dem, in_source_uri, in_absorption_rate_uri],
        [flow_direction_uri, dem_uri, source_uri, absorption_rate_uri],
        ["nearest", "nearest", "nearest", "nearest"], out_pixel_size,
        "intersection", 0, aoi_uri=aoi_uri, assert_datasets_projected=False)

    outflow_weights_uri = raster_utils.temporary_filename(suffix='.tif')
    outflow_direction_uri = raster_utils.temporary_filename(suffix='.tif')

    LOGGER.info("finding sinks")
    sink_cell_set = routing_cython_core.find_sinks(dem_uri)
    LOGGER.info("calculating flow_graph")
    routing_cython_core.calculate_flow_weights(
        flow_direction_uri, outflow_weights_uri, outflow_direction_uri)

    LOGGER.debug('sinks: %s' % str(sink_cell_set))
    LOGGER.info("calculating transport")
    LOGGER.debug('absorption_rate_uri %s' % absorption_rate_uri)
    routing_cython_core.calculate_transport(
        outflow_direction_uri, outflow_weights_uri, sink_cell_set,
        source_uri, absorption_rate_uri, loss_uri, flux_uri, absorption_mode, stream_uri)


def flow_accumulation(flow_direction_uri, dem_uri, flux_output_uri, aoi_uri=None):
    """A helper function to calculate flow accumulation, also returns
        intermediate rasters for future calculation.

        flow_direction_uri - a uri to a raster that has d-infinity flow
            directions in it
        dem_uri - a uri to a gdal dataset representing a DEM, must be aligned
            with flow_direction_uri
        flux_output_uri - location to dump the raster representing flow
            accumulation
        aoi_uri - (optional) uri to a datasource to mask out the dem"""

    LOGGER.debug("starting flow_accumulation")
    constant_flux_source_uri = raster_utils.temporary_filename(suffix='.tif')
    zero_absorption_source_uri = raster_utils.temporary_filename(suffix='.tif')
    loss_uri = raster_utils.temporary_filename(suffix='.tif')

    LOGGER.debug("creating constant rasters")
    raster_utils.make_constant_raster_from_base_uri(
        dem_uri, 1.0, constant_flux_source_uri)
    raster_utils.make_constant_raster_from_base_uri(
        dem_uri, 0.0, zero_absorption_source_uri)

    LOGGER.debug("routing flux")
    route_flux(
        flow_direction_uri, dem_uri, constant_flux_source_uri,
        zero_absorption_source_uri, loss_uri, flux_output_uri, 'flux_only',
        aoi_uri=aoi_uri)


def stream_threshold(flow_accumulation_uri, flow_threshold, stream_uri):
    """Creates a raster of accumulated flow to each cell.

        flow_accumulation_data - (input) A flow accumulation dataset of type
            floating point
        flow_threshold - (input) a number indicating the threshold to declare
            a pixel a stream or no
        stream_uri - (input) the uri of the output stream dataset

        returns nothing"""
    
    flow_nodata = raster_utils.get_nodata_from_uri(flow_accumulation_uri)
    def classify_stream(flow_accumulation):
        #mask and convert to 0/1
        #flow_thrshold might come in as a string all across the invest models
        #this just casts it so it doesn't break someone's model
        stream_mask = (flow_accumulation >= float(flow_threshold)).astype(numpy.byte)
        return numpy.where(flow_accumulation != flow_nodata, stream_mask, 255)
        
    raster_utils.vectorize_datasets(
        [flow_accumulation_uri], classify_stream, stream_uri, gdal.GDT_Byte, 
        255, raster_utils.get_cell_size_from_uri(flow_accumulation_uri),
        'intersection', vectorize_op=False, assert_datasets_projected=False)


def calculate_flow_length(flow_direction_uri, flow_length_uri):
    """Calculate the flow length of a cell given the flow direction

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

    flow_length_pixel_size = raster_utils.get_cell_size_from_uri(flow_length_uri)

    def flow_length(flow_direction):
        """Function to calculate flow length for vectorize_datasets"""
        if flow_direction == flow_direction_nodata:
            return flow_length_nodata
        sin_val = numpy.abs(numpy.sin(flow_direction))
        cos_val = numpy.abs(numpy.cos(flow_direction))
        return flow_length_pixel_size / numpy.maximum(sin_val, cos_val)

    cell_size = raster_utils.get_cell_size_from_uri(flow_direction_uri)
    raster_utils.vectorize_datasets(
        [flow_direction_uri], flow_length, flow_length_uri, gdal.GDT_Float32,
        flow_length_nodata, cell_size, "intersection")


def pixel_amount_exported(
    in_flow_direction_uri, in_dem_uri, in_stream_uri, in_retention_rate_uri,
    in_source_uri, pixel_export_uri, aoi_uri=None, percent_to_stream_uri=None):
    """Calculates flow and absorption rates to determine the amount of source
        exported to the stream.  All datasets must be in the same projection.
        Nothing will be retained on stream pixels.

        in_dem_uri - a dem dataset used to determine flow directions
        in_stream_uri - an integer dataset representing stream locations.
            0 is no stream 1 is a stream
        in_retention_rate_uri - a dataset representing per pixel retention
            rates
        in_source_uri - a dataset representing per pixel export
        pixel_export_uri - the output dataset uri to represent the amount
            of source exported to the stream
        percent_to_stream_uri - (optional) if defined is the raster that's the
            percent of export to the stream layer

        returns nothing"""

    #Align all the input rasters since the cython core requires them to line up
    out_pixel_size = raster_utils.get_cell_size_from_uri(in_dem_uri)
    dem_uri = raster_utils.temporary_filename(suffix='.tif')
    stream_uri = raster_utils.temporary_filename(suffix='.tif')
    retention_rate_uri = raster_utils.temporary_filename(suffix='.tif')
    source_uri = raster_utils.temporary_filename(suffix='.tif')
    flow_direction_uri = raster_utils.temporary_filename(suffix='.tif')
    raster_utils.align_dataset_list(
        [in_flow_direction_uri, in_dem_uri, in_stream_uri, in_retention_rate_uri, in_source_uri],
        [flow_direction_uri, dem_uri, stream_uri, retention_rate_uri, source_uri],
        ["nearest", "nearest", "nearest", "nearest", "nearest"], out_pixel_size,
        "intersection", 0, aoi_uri=aoi_uri)

    #Calculate export rate
    export_rate_uri = raster_utils.temporary_filename(suffix='.tif')
    nodata_retention = raster_utils.get_nodata_from_uri(retention_rate_uri)
    def retention_to_export(retention):
        """calculates 1.0-input unles it's nodata"""
        if retention == nodata_retention:
            return nodata_retention
        return 1.0 - retention
    raster_utils.vectorize_datasets(
        [retention_rate_uri], retention_to_export, export_rate_uri,
        gdal.GDT_Float32, nodata_retention, out_pixel_size, "intersection",
        dataset_to_align_index=0)

    #Calculate flow direction and weights
    outflow_weights_uri = raster_utils.temporary_filename(suffix='.tif')
    outflow_direction_uri = raster_utils.temporary_filename(suffix='.tif')
    routing_cython_core.calculate_flow_weights(
        flow_direction_uri, outflow_weights_uri, outflow_direction_uri)

    #Calculate the percent to sink
    if percent_to_stream_uri is not None:
        effect_uri = percent_to_stream_uri
    else:
        effect_uri = raster_utils.temporary_filename(suffix='.tif')
        
    routing_cython_core.percent_to_sink(
        stream_uri, export_rate_uri, outflow_direction_uri,
        outflow_weights_uri, effect_uri)

    #Finally multiply the effect by the source
    nodata_source = raster_utils.get_nodata_from_uri(source_uri)
    nodata_effect = raster_utils.get_nodata_from_uri(effect_uri)
    nodata_stream = raster_utils.get_nodata_from_uri(stream_uri)
    def mult_nodata(source, effect, stream):
        """Does the multiply of source by effect if there's not a stream"""
        if source == nodata_source or effect == nodata_effect or \
                stream == nodata_stream:
            return nodata_source
        return source * effect * (1 - stream)
    raster_utils.vectorize_datasets(
        [source_uri, effect_uri, stream_uri], mult_nodata, pixel_export_uri,
        gdal.GDT_Float32, nodata_source, out_pixel_size, "intersection",
        dataset_to_align_index=0)


def calculate_stream(dem_uri, flow_threshold, stream_uri):
    """A wrapper to calculate streams given a dem and a flow threshold.
        The function will calcluate the flow accumulation then threshold
        that to calcualte streams.  Useful to sidestep separate flow
        accumulation.

        dem_uri - a uri to a gdal dataset describing the dem
        flow_threshold - the value to determine if a flow pixel is a stream
            pixel
        stream_uri - a uri to an output dataset that will have pixels
            listed a 0 for no stream or 1 for stream or nodata outside the dem

        returns nothing"""

    flow_accumulation_uri = raster_utils.temporary_filename(suffix='.tif')
    flow_direction_uri = raster_utils.temporary_filename(suffix='.tif')
    dem_offset_uri = raster_utils.temporary_filename(suffix='.tif')

    routing_cython_core.resolve_flat_regions_for_drainage(
        dem_uri, dem_offset_uri)
    routing_cython_core.flow_direction_inf(dem_offset_uri, flow_direction_uri)
    flow_accumulation(
        flow_direction_uri, dem_offset_uri, flow_accumulation_uri)
    stream_threshold(flow_accumulation_uri, flow_threshold, stream_uri)


def flow_direction_inf(dem_uri, flow_direction_uri):
    """Calculates the D-infinity flow algorithm.  The output is a float
        raster whose values range from 0 to 2pi.
        Algorithm from: Tarboton, "A new method for the determination of flow
        directions and upslope areas in grid digital elevation models," Water
        Resources Research, vol. 33, no. 2, pages 309 - 319, February 1997.

       dem_uri - (input) a uri to a single band GDAL Dataset with elevation
           values
       flow_direction_uri - (output) a uri to a single band GDAL dataset
           with d infinity flow directions in it.

       returns nothing"""
    routing_cython_core.flow_direction_inf(dem_uri, flow_direction_uri)


def fill_pits(dem_uri, dem_out_uri):
    """This function fills regions in a DEM that don't drain to the edge
        of the dataset.  The resulting DEM will likely have plateaus where the
        pits are filled.
        
        dem_uri - the original dem URI
        dem_out_uri - the original dem with pits raised to the highest drain
            value
            
        returns nothing"""
    routing_cython_core.fill_pits(dem_uri, dem_out_uri)
    

def resolve_flat_regions_for_drainage(dem_uri, dem_out_uri):
    """This function resolves the flat regions on a DEM that cause undefined
        flow directions to occur during routing.  The algorithm is the one
        presented in "The assignment of drainage direction over float surfaces
        in raster digital elevation models by Garbrecht and Martz (1997)
        
        dem_carray - a chunked floating point array that represents a digital
            elevation model.  Any flat regions that would cause an undefined
            flow direction will be adjusted in height so that every pixel
            on the dem has a local defined slope.

        nodata_value - this value will be ignored on the DEM as a valid height
            value
            
        returns nothing"""
    routing_cython_core.resolve_flat_regions_for_drainage(dem_uri, dem_out_uri)


def distance_to_stream(flow_direction_uri, stream_uri, distance_uri, factor_uri=None):
    """This function calculates the flow downhill distance to the stream layers
    
        flow_direction_uri - a raster with d-infinity flow directions
        stream_uri - a raster where 1 indicates a stream all other values
            ignored must be same dimensions and projection as
            flow_direction_uri)
        distance_uri - an output raster that will be the same dimensions as
            the input rasters where each pixel is in linear units the drainage
            from that point to a stream.
            
        returns nothing"""
        
    routing_cython_core.distance_to_stream(
        flow_direction_uri, stream_uri, distance_uri, factor_uri=factor_uri)
