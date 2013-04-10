"""Module that contains the core computational components for the carbon model
    including the biophysical and valuation functions"""

import logging
import bisect

import numpy
from osgeo import gdal

from invest_natcap import raster_utils
import sediment_cython_core

LOGGER = logging.getLogger('sediment_core')


def calculate_ls_factor(flow_accumulation_uri, slope_uri, 
                        aspect_uri, ls_factor_uri, ls_nodata):
    """Calculates the LS factor as Equation 3 from "Extension and validation 
        of a geographic information system-based method for calculating the
        Revised Universal Soil Loss Equation length-slope factor for erosion
        risk assessments in large watersheds"   

        (Required that all raster inputs are same dimensions and projections
        and have square cells)
        flow_accumulation_uri - a uri to a  single band raster of type float that
            indicates the contributing area at the inlet of a grid cell
        slope_uri - a uri to a single band raster of type float that indicates
            the slope at a pixel given as a percent
        aspect_uri - a uri to a single band raster of type float that indicates the
            direction that slopes are facing in terms of radians east and
            increase clockwise: pi/2 is north, pi is west, 3pi/2, south and
            0 or 2pi is east.
        ls_factor_uri - (input) a string to the path where the LS raster will
            be written

        returns nothing"""
    
    flow_accumulation_nodata = raster_utils.get_nodata_from_uri(
        flow_accumulation_uri)
    slope_nodata = raster_utils.get_nodata_from_uri(slope_uri)
    aspect_nodata = raster_utils.get_nodata_from_uri(aspect_uri)

    #Assumes that cells are square
    cell_size = raster_utils.get_cell_size_from_uri(flow_accumulation_uri)
    cell_area = cell_size ** 2

    def ls_factor_function(aspect_angle, slope, flow_accumulation):
        """Calculate the ls factor

            aspect_angle - flow direction in radians
            slope - slope in terms of percent
            flow_accumulation - upstream pixels at this point

            returns the ls_factor calculation for this point"""

        return sediment_cython_core.ls_factor_function(
            float(aspect_angle), float(slope), float(flow_accumulation), float(aspect_nodata), float(slope_nodata), float(flow_accumulation_nodata), float(ls_nodata), float(cell_area), float(cell_size))

    #Call vectorize datasets to calculate the ls_factor
    dataset_uri_list = [aspect_uri, slope_uri, flow_accumulation_uri]
    raster_utils.vectorize_datasets(
        dataset_uri_list, ls_factor_function, ls_factor_uri, gdal.GDT_Float32,
            ls_nodata, cell_size, "intersection", dataset_to_align_index=0)


def calculate_rkls(
    ls_factor_uri, erosivity_uri, erodibility_uri, stream_uri,
    rkls_uri):

    """Calculates per-pixel potential soil loss using the RKLS (revised 
        universial soil loss equation with no C or P).

        ls_factor_uri - GDAL uri with the LS factor pre-calculated
        erosivity_uri - GDAL uri with per pixel erosivity 
        erodibility_uri - GDAL uri with per pixel erodibility
        stream_uri - GDAL uri indicating locations with streams
            (0 is no stream, 1 stream)
        rkls_uri - string input indicating the path to disk
            for the resulting potential soil loss raster

        returns nothing"""

    ls_factor_nodata = raster_utils.get_nodata_from_uri(ls_factor_uri)
    erosivity_nodata = raster_utils.get_nodata_from_uri(erosivity_uri)
    erodibility_nodata = raster_utils.get_nodata_from_uri(erodibility_uri)
    stream_nodata = raster_utils.get_nodata_from_uri(stream_uri)
    usle_nodata = -1.0

    cell_size = raster_utils.get_cell_size_from_uri(ls_factor_uri)
    cell_area = cell_size ** 2

    def rkls_function(ls_factor, erosivity, erodibility, v_stream):
        """Calculates the USLE equation
        
        ls_factor - length/slope factor
        erosivity - related to peak rainfall events
        erodibility - related to the potential for soil to erode
        v_stream - 1 or 0 depending if there is a stream there.  If so, no
            potential soil loss due to USLE
        
        returns ls_factor * erosivity * erodibility * usle_c_p if all arguments
            defined, nodata if some are not defined, 0 if in a stream
            (v_stream)"""

        if (ls_factor == ls_factor_nodata or erosivity == erosivity_nodata or 
            erodibility == erodibility_nodata or v_stream == stream_nodata):
            return usle_nodata
        if v_stream == 1:
            return 0.0
        #current unit is tons/ha, multiply by ha/cell (cell area in m^2/100**2)
        return ls_factor * erosivity * erodibility * cell_area / 10000.0

    dataset_uri_list = [
        ls_factor_uri, erosivity_uri, erodibility_uri, stream_uri]

    #Aligning with index 3 that's the stream and the most likely to be
    #aligned with LULCs
    raster_utils.vectorize_datasets(
        dataset_uri_list, rkls_function, rkls_uri, gdal.GDT_Float32,
        usle_nodata, cell_size, "intersection", dataset_to_align_index=3)
