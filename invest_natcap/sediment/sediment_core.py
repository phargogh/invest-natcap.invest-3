"""Module that contains the core computational components for the carbon model
    including the biophysical and valuation functions"""

import logging

import numpy as np
from osgeo import gdal

import invest_cython_core
from invest_natcap.invest_core import invest_core

LOGGER = logging.getLogger('sediment_core')

def biophysical(args):
    """Executes the basic sediment model

        args - is a dictionary with at least the following entries:
        args['dem'] - a digital elevation raster file (required)
        args['erosivity'] - an input raster describing the 
            rainfall eroisivity index (required)
        args['erodibility'] - an input raster describing soil 
            erodibility (required)
        args['landuse'] - a land use/land cover raster whose
            LULC indexes correspond to indexs in the biophysical table input.
            Used for determining soil retention and other biophysical 
            properties of the landscape.  (required)
        args['watersheds'] - an input shapefile of the watersheds
            of interest as polygons. (required)
        args['subwatersheds'] - an input shapefile of the 
            subwatersheds of interest that are contained in the
            'watersheds' shape provided as input. (required)
        args['usle_uri'] - a URI location to the temporary USLE raster
        args['reservoir_locations'] - an input shape file with 
            points indicating reservoir locations with IDs. (optional)
        args['reservoir_properties'] - an input CSV table 
            describing properties of input reservoirs provided in the 
            reservoirs shapefile (optional)
        args['biophysical_table'] - an input CSV file with 
            biophysical information about each of the land use classes.
        args['threshold_flow_accumulation'] - an integer describing the number
            of upstream cells that must flow int a cell before it's considered
            part of a stream.  required if 'v_stream' is not provided.
        args['slope_threshold'] - A percentage slope threshold as described in
            the user's guide.
        args['slope'] - an output raster file that holds the slope percentage
            as a proporition from the dem
        args['ls_factor'] - an output raster file containing the ls_factor
            calculated on the particular dem
        args['v_stream_out'] - An output raster file that classifies the
            watersheds into stream and non-stream regions based on the
            value of 'threshold_flow_accumulation'
        args['flow_direction'] - An output raster indicating the flow direction
            on each pixel
        args['sret_dr'] - An output raster showing the amount of sediment
            retained on each pixel during routing.
            
        returns nothing"""

    LOGGER.info("calculating flow direction")
    invest_cython_core.flow_direction_inf(args['dem'], args['flow_direction'])

    LOGGER.info("calculating flow accumulation")
    invest_cython_core.flow_accumulation_dinf(args['flow_direction'],
                                              args['flow_accumulation'],
                                              args['dem'])

    invest_cython_core.calculate_slope(args['dem'], args['slope'])

    LOGGER.info("calculating LS factor accumulation")
    invest_cython_core.calculate_ls_factor(args['flow_accumulation'],
                                           args['slope'],
                                           args['flow_direction'],
                                           args['ls_factor'])

    #Nodata value to use for output raster
    usle_nodata = -1.0

    #map lulc to a usle_c * usle_p raster
    LOGGER.info('mapping landuse types to crop and practice management values')
    usle_c_p_raster = invest_cython_core.newRasterFromBase(args['landuse'], '',
        'MEM', usle_nodata, gdal.GDT_Float32)
    def lulc_to_cp(lulc_code):
        """This is a helper function that's used to map an LULC code to the
            C * P values needed by the sediment model and defined
            in the biophysical table in the closure above.  The intent is this
            function is used in a vectorize operation for a single raster.
            
            lulc_code - an integer representing a LULC value in a raster
            
            returns C*P where C and P are defined in the 
                args['biophysical_table']
        """
        #There are string casts here because the biophysical table is all 
        #strings thanks to the csv table conversion.
        if str(lulc_code) not in args['biophysical_table']:
            return usle_nodata
        #We need to divide the c and p factors by 1000 (10*6 == 1000*1000) 
        #because they're stored in the table as C * 1000 and P * 1000.  See 
        #the user's guide:
        #http://ncp-dev.stanford.edu/~dataportal/invest-releases/documentation/2_2_0/sediment_retention.html
        return float(args['biophysical_table'][str(lulc_code)]['usle_c']) * \
            float(args['biophysical_table'][str(lulc_code)]['usle_p']) / \
                10 ** 6
    invest_core.vectorize1ArgOp(args['landuse'].GetRasterBand(1), lulc_to_cp,
                                usle_c_p_raster.GetRasterBand(1))

    #Set up structures for USLE calculation
    ls_nodata = args['ls_factor'].GetRasterBand(1).GetNoDataValue()
    erosivity_nodata = args['erosivity'].GetRasterBand(1).GetNoDataValue()
    erodibility_nodata = args['erodibility'].GetRasterBand(1).GetNoDataValue()



    def mult_all(ls_factor, erosivity, erodibility, usle_c_p):
        if ls_factor == usle_nodata or erosivity == usle_nodata or \
            erodibility == usle_nodata or usle_c_p == usle_nodata:
            return usle_nodata
        return ls_factor * erosivity * erodibility * usle_c_p
    mult_op = np.vectorize(mult_all)

    LOGGER.info("calculating potential soil loss")

    potential_soil_loss = invest_core.vectorizeRasters([args['ls_factor'],
        args['erosivity'], args['erodibility'], usle_c_p_raster], mult_op,
        args['usle_uri'], nodata=usle_nodata)

    #change units from tons per hectare to tons per cell.  We need to do this
    #after the vectorize raster operation since we won't know the cell size
    #until then.  Convert cell_area to meters (in Ha by default)
    cell_area = invest_cython_core.pixelArea(potential_soil_loss) * (10 ** 4)
    LOGGER.debug("{cell_area: %s" % cell_area)
    potential_soil_loss_matrix = potential_soil_loss.GetRasterBand(1). \
        ReadAsArray(0, 0, potential_soil_loss.RasterXSize,
                    potential_soil_loss.RasterYSize)
    potential_soil_loss_nodata = \
        potential_soil_loss.GetRasterBand(1).GetNoDataValue()
    potential_soil_loss_nodata_mask = \
        potential_soil_loss_matrix == potential_soil_loss_nodata
    potential_soil_loss_matrix *= cell_area / 10000.0
    potential_soil_loss_matrix[potential_soil_loss_nodata_mask] = \
        potential_soil_loss_nodata
    #Get rid of any negative values due to outside interpolation:
    potential_soil_loss_matrix[potential_soil_loss_matrix < 0] = \
        potential_soil_loss_nodata
    potential_soil_loss.GetRasterBand(1). \
        WriteArray(potential_soil_loss_matrix, 0, 0)
    invest_core.calculateRasterStats(potential_soil_loss.GetRasterBand(1))

    #map lulc to a usle_c * usle_p raster
    LOGGER.info('mapping landuse types to vegetation retention efficiencies')
    retention_efficiency_raster_raw = \
        invest_cython_core.newRasterFromBase(args['landuse'], '', 'MEM',
                                             usle_nodata, gdal.GDT_Float32)

    def lulc_to_retention(lulc_code):
        """This is a helper function that's used to map an LULC code to the
            retention values needed by the sediment model and defined
            in the biophysical table in the closure above.  The intent is this
            function is used in a vectorize operation for a single raster.
            
            lulc_code - an integer representing a LULC value in a raster
            
            returns C*P where C and P are defined in the 
                args['biophysical_table']
        """
        #There are string casts here because the biophysical table is all 
        #strings thanks to the csv table conversion.
        if str(lulc_code) not in args['biophysical_table']:
            return usle_nodata
        #We need to divide the retention efficiency by 100  because they're 
        #stored in the table as sedret_eff * 100.  See the user's guide:
        #http://ncp-dev.stanford.edu/~dataportal/invest-releases/documentation/2_2_0/sediment_retention.html
        return float(args['biophysical_table'] \
                     [str(lulc_code)]['sedret_eff']) / 100.0

    sret_dr_raw = invest_cython_core.newRasterFromBase(potential_soil_loss,
        '', 'MEM', -1.0, gdal.GDT_Float32)
    invest_core.vectorize1ArgOp(args['landuse'].GetRasterBand(1),
        lulc_to_retention, retention_efficiency_raster_raw.GetRasterBand(1))

    #now interpolate retention_efficiency_raster_raw to a raster that will
    #overlay potential_soil_loss
    def return_efficiency(soil_loss, efficiency):
        """This is a function that's used to bastardize the interpolation and
            cropping properties of vectorizeRaster.  We want the output to
            be an interpolated efficiency raster that's the same size and
            resolution of soil_loss.  So we vectorize over two rasters but
            just return efficiency.  Oh what I do for a good PEP8 score.
            
            soil_loss - ignored
            efficiency - return that
            
            returns efficiency
        """
        return efficiency
    mult_op = np.vectorize(return_efficiency)
    retention_efficiency_raster = \
        invest_core.vectorizeRasters([potential_soil_loss,
            retention_efficiency_raster_raw], mult_op, nodata=usle_nodata)

    #Create an output raster for routed sediment retention
    sret_dr = invest_cython_core.newRasterFromBase(potential_soil_loss,
        args['sret_dr_uri'], 'GTiff', -1.0, gdal.GDT_Float32)

    #Route the sediment across the landscape and store the amount retained
    #per pixel
    LOGGER.debug('potential soil loss dimensions %s %s' % \
                 (potential_soil_loss.RasterXSize, \
                  potential_soil_loss.RasterYSize))
    LOGGER.debug('args["flow_direction"] dimensions %s %s' % \
                 (args['flow_direction'].RasterXSize, \
                  args['flow_direction'].RasterYSize))
    LOGGER.debug('retention_efficiency_raster dimensions %s %s' % \
                 (retention_efficiency_raster.RasterXSize, \
                  retention_efficiency_raster.RasterYSize))
    LOGGER.debug('sret_dr dimensions %s %s' % \
                 (sret_dr.RasterXSize, sret_dr.RasterYSize))
    invest_cython_core.calc_retained_sediment(potential_soil_loss,
        args['flow_direction'], retention_efficiency_raster, sret_dr)

def valuation(args):
    """Executes the basic carbon model that maps a carbon pool dataset to a
        LULC raster.
    
        args - is a dictionary with the following entries:
        
        returns nothing"""

    LOGGER.info('not implemented yet')
