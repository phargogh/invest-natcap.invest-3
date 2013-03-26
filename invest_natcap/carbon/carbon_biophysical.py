"""InVEST Carbon biophysical module at the "uri" level"""

import sys
import os
import math
import json
import logging

from osgeo import gdal
from osgeo import ogr

try:
    import carbon_core
except ImportError:
    from invest_natcap.carbon import carbon_core

from invest_natcap import raster_utils



logging.basicConfig(format='%(asctime)s %(name)-18s %(levelname)-8s \
    %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

LOGGER = logging.getLogger('carbon_biophysical')

def execute(args):
    execute_30(**args)

def execute_30(**args):
    """This function invokes the carbon model given URI inputs of files.
        It will do filehandling and open/create appropriate objects to 
        pass to the core carbon biophysical processing function.  It may write
        log, warning, or error messages to stdout.
        
        args - a python dictionary with at the following possible entries:
        args['workspace_dir'] - a uri to the directory that will write output
            and other temporary files during calculation. (required)
        args['lulc_cur_uri'] - is a uri to a GDAL raster dataset (required)
        args['carbon_pools_uri'] - is a uri to a DBF dataset mapping carbon 
            storage density to the lulc classifications specified in the
            lulc rasters. (required) 
        args['lulc_fut_uri'] - is a uri to a GDAL raster dataset (optional
         if calculating sequestration)
        args['lulc_cur_year'] - An integer representing the year of lulc_cur 
            used in HWP calculation (required if args contains a 
            'hwp_cur_shape_uri', or 'hwp_fut_shape_uri' key)
        args['lulc_fut_year'] - An integer representing the year of  lulc_fut
            used in HWP calculation (required if args contains a 
            'hwp_fut_shape_uri' key)
        args['hwp_cur_shape_uri'] - Current shapefile uri for harvested wood 
            calculation (optional, include if calculating current lulc hwp) 
        args['hwp_fut_shape_uri'] - Future shapefile uri for harvested wood 
            calculation (optional, include if calculating future lulc hwp)
        
        returns nothing."""

    output_dir = os.path.join(args['workspace_dir'], 'output')
    intermediate_dir = os.path.join(args['workspace_dir'], 'intermediate')
    for directory in [output_dir, intermediate_dir]:
        if not os.path.exists(directory):
            LOGGER.info('creating directory %s', directory)
            os.makedirs(directory)

    #1) load carbon pools into dictionary indexed by LULC
    LOGGER.debug("building carbon pools")
    pools = raster_utils.get_lookup_from_table(args['carbon_pools_uri'], 'LULC')

    #2) map lulc_cur and _fut (if availble) to total carbon
    for lulc_uri in ['lulc_cur_uri', 'lulc_fut_uri']:
        if lulc_uri in args:
            scenario_type = lulc_uri.split('_')[-2] #get the 'cur' or 'fut'
            cell_area_ha = (
                raster_utils.get_cell_area_from_uri(args[lulc_uri]) /
                10000.0)

            for lulc_id, lookup_dict in pools.iteritems():
                pools[lulc_id]['total_%s' % lulc_uri] = sum(
                    [pools[lulc_id][pool_type] for pool_type in
                     ['c_above', 'c_below', 'c_soil', 'c_dead']]) * cell_area_ha

            nodata = raster_utils.get_nodata_from_uri(args[lulc_uri])
            nodata_out = -1.0
            def map_carbon_pool(lulc):
                if lulc == nodata:
                    return nodata_out
                return pools[lulc]['total_%s' % lulc_uri]
            dataset_out_uri = os.path.join(
                output_dir, 'tot_C_%s.tif' % scenario_type)
            pixel_size_out = raster_utils.get_cell_size_from_uri(args[lulc_uri])
            raster_utils.vectorize_datasets(
                [args[lulc_uri]], map_carbon_pool, dataset_out_uri,
                gdal.GDT_Float32, nodata_out, pixel_size_out,
                "intersection", dataset_to_align_index=0)

            #Add calculate the hwp storage, if it is passed as an input argument
            hwp_key = 'hwp_%s_shape_uri' % scenario_type
            if hwp_key in args:
                c_hwp_uri = os.path.join(intermediate_dir, 'c_hwp_%s.tif' % scenario_type)
                bio_hwp_uri = os.path.join(intermediate_dir, 'bio_hwp_%s.tif' % scenario_type)
                vol_hwp_uri = os.path.join(intermediate_dir, 'vol_hwp_%s.tif' % scenario_type)

                if scenario_type == 'cur':
                    calculate_hwp_storage_cur(
                        args[hwp_key], args[lulc_uri], c_hwp_uri, bio_hwp_uri,
                        vol_hwp_uri, args['lulc_%s_year' % scenario_type])
                elif scenario_type == 'fut':
                    hwp_shapes = {}

                    if 'hwp_cur_shape_uri' in args:
                        hwp_shapes['cur'] = args['hwp_cur_shape_uri']
                    if 'hwp_fut_shape_uri' in args:
                        hwp_shapes['fut'] = args['hwp_fut_shape_uri']

                    calculate_hwp_storage_fut(
                        hwp_shapes, args[lulc_uri], c_hwp_uri, bio_hwp_uri,
                        vol_hwp_uri, args['lulc_cur_year'], args['lulc_fut_year'])

                    
        #3) burn hwp_{cur/fut} into rasters


    return

    #TODO:
    #4) if _fut, calculate sequestration

    gdal.AllRegister()

    #Load and copy relevant inputs from args into a dictionary that
    #can be passed to the biophysical core model
    biophysicalArgs = {}

    #map lulc to carbon pool
#    nodata_carbon = -1.0
#    cur_carbon_uri = os.path.join(args['workspace_dir'], 'cur_carbon.tif')
#    raster_utils.reclassify_dataset_uri(
#        args['lulc_cur_uri'], carbon_pool_map, cur_carbon_uri, gdal.GDT_Float32,
#        nodata_carbon, exception_flag='values_required')

    #lulc_cur is always required
    LOGGER.debug('loading %s', args['lulc_cur_uri'])
    biophysicalArgs['lulc_cur'] = gdal.Open(str(args['lulc_cur_uri']),
                                            gdal.GA_ReadOnly)

    #a future lulc is only required if sequestering or hwp calculating
    if 'lulc_fut_uri' in args:
        LOGGER.debug('loading %s', args['lulc_fut_uri'])
        biophysicalArgs['lulc_fut'] = gdal.Open(str(args['lulc_fut_uri']),
                                            gdal.GA_ReadOnly)

    #Years and harvest shapes are required if doing HWP calculation
    for x in ['lulc_cur_year', 'lulc_fut_year']:
        if x in args: biophysicalArgs[x] = args[x]
    fsencoding = sys.getfilesystemencoding()
    for x in ['hwp_cur_shape', 'hwp_fut_shape']:
        uriName = x + '_uri'
        if uriName in args:
            LOGGER.debug('loading %s', str(args[uriName]))
            biophysicalArgs[x] = ogr.Open(str(args[uriName]).encode(fsencoding))

    #Always need carbon pools, if uncertainty calculation they also need
    #to have range columns in them, but no need to check at this level.
    LOGGER.debug('loading %s', args['carbon_pools_uri'])

    #setting readOnly true because we won't write to it
    biophysicalArgs['carbon_pools'] = dbf.Dbf(args['carbon_pools_uri'], 
                                              readOnly=True)

    #At this point all inputs are loaded into biophysicalArgs.  The 
    #biophysical model also needs temporary and output files to do its
    #calculation.  These are calculated next.

    #These lines sets up the output directory structure for the workspace
    outputDirectoryPrefix = args['workspace_dir'] + os.sep + 'Output' + os.sep
    intermediateDirectoryPrefix = args['workspace_dir'] + os.sep + \
        'Intermediate' + os.sep
    for d in [outputDirectoryPrefix, intermediateDirectoryPrefix]:
        if not os.path.exists(d):
            LOGGER.debug('creating directory %s', d)
            os.makedirs(d)

    #This defines a dictionary that links output/temporary GDAL/OAL objects
    #to their locations on disk.  Helpful for creating the objects in the 
    #next step
    outputURIs = {}

    #make a list of all the rasters that we need to create, it's dependant
    #on what calculation mode we're in (sequestration, HWP, uncertainty, etc.)
    outputRasters = ['tot_C_cur']
    if 'lulc_fut_uri' in args:
        outputRasters.extend(['tot_C_fut', 'sequest'])
    #build the URIs for the output rasters in a single loop
    for key in outputRasters:
        outputURIs[key] = outputDirectoryPrefix + key + '.tif'

    intermediateRasters = ['storage_cur']

    #If we're doing a HWP calculation, we need temporary rasters to hold the
    #HWP pools, name them the same as the key but add a .tif extension
    if 'hwp_cur_shape_uri' in args:
        for key in ['c_hwp_cur', 'bio_hwp_cur', 'vol_hwp_cur']:
            outputURIs[key] = intermediateDirectoryPrefix + key + ".tif"
    if 'hwp_fut_shape_uri' in args:
        for key in ['c_hwp_fut', 'bio_hwp_fut', 'vol_hwp_fut']:
            outputURIs[key] = intermediateDirectoryPrefix + key + ".tif"

    #Create the output and intermediate rasters to be the same size/format as
    #the base LULC
    for rasterName, rasterPath in outputURIs.iteritems():
        LOGGER.debug('creating output raster %s', rasterPath)
        biophysicalArgs[rasterName] = \
            raster_utils.new_raster_from_base(biophysicalArgs['lulc_cur'],
                              rasterPath, 'GTiff', -5.0, gdal.GDT_Float32)

    #run the biophysical part of the carbon model.
    LOGGER.info('starting carbon biophysical model')
    carbon_core.biophysical(biophysicalArgs)
    LOGGER.info('finished carbon biophysical model')
    
    #Dump some info about total carbon stats
#    carbon_core.calculate_summary(biophysicalArgs)


def calculate_hwp_storage_cur(
    hwp_shape_uri, base_dataset_uri, c_hwp_uri, bio_hwp_uri, vol_hwp_uri,
    yr_cur):
    """Calculates carbon storage, hwp biomassPerPixel and volumePerPixel due 
        to harvested wood products in parcels on current landscape.
        
        hwp_shape - oal shapefile indicating harvest map of interest
        base_dataset_uri - a gdal dataset to create the output rasters from
        c_hwp - an output GDAL rasterband representing  carbon stored in 
            harvested wood products for current calculation 
        bio_hwp - an output GDAL rasterband representing carbon stored in 
            harvested wood products for land cover under interest
        vol_hwp - an output GDAL rasterband representing carbon stored in
             harvested wood products for land cover under interest
        yr_cur - year of the current landcover map
        
        No return value"""

    ############### Start
    pixel_area = raster_utils.get_cell_size_from_uri(base_dataset_uri) ** 2 / 10000.0 #convert to Ha
    hwp_shape = ogr.Open(hwp_shape_uri)
    base_dataset = gdal.Open(base_dataset_uri)
    nodata = -1.0
    c_hwp = raster_utils.new_raster_from_base(base_dataset, c_hwp_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)
    bio_hwp = raster_utils.new_raster_from_base(base_dataset, bio_hwp_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)
    vol_hwp = raster_utils.new_raster_from_base(base_dataset, vol_hwp_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)

    #Create a temporary shapefile to hold values of per feature carbon pools
    #HWP biomassPerPixel and volumePerPixel, will be used later to rasterize 
    #those values to output rasters
    hwp_shape_copy = ogr.GetDriverByName('Memory').CopyDataSource(hwp_shape, '')
    hwp_shape_layer_copy = hwp_shape_copy.GetLayer()

    #Create fields in the layers to hold hardwood product pools, 
    #biomassPerPixel and volumePerPixel
    calculated_attribute_names = ['c_hwp_pool', 'bio_hwp', 'vol_hwp']
    for x in calculated_attribute_names:
        field_def = ogr.FieldDefn(x, ogr.OFTReal)
        hwp_shape_layer_copy.CreateField(field_def)

    #Visit each feature and calculate the carbon pool, biomassPerPixel, and 
    #volumePerPixel of that parcel
    for feature in hwp_shape_layer_copy:
        #This makes a helpful dictionary to access fields in the feature
        #later in the code
        field_args = _get_fields(feature)

        if 'start_date' not in field_args or 'cut_cur' not in field_args:
            continue

        LOGGER.debug('calculate_hwp_storage_cur %s ' % field_args)

        #If start date and/or the amount of carbon per cut is zero, it doesn't
        #make sense to do any calculation on carbon pools or 
        #biomassPerPixel/volumePerPixel
        if field_args['start_date'] != 0 and field_args['cut_cur'] != 0:

            time_span = yr_cur - field_args['start_date']
            start_years = time_span

            #Calculate the carbon pool due to decaying HWP over the time_span
            feature_carbon_storage_per_pixel = (
                pixel_area * _carbon_pool_in_hwp_from_parcel(
                    field_args['cut_cur'], time_span, start_years,
                    field_args['freq_cur'], field_args['decay_cur']))

            #Next lines caculate biomassPerPixel and volumePerPixel of 
            #harvested wood
            number_of_harvests = \
                math.ceil(time_span / float(field_args['freq_cur']))

            biomass_in_feature = field_args['cut_cur'] * number_of_harvests / \
                float(field_args['c_den_cur'])

            biomass_per_pixel = biomass_in_feature * pixel_area

            volume_per_pixel = biomass_per_pixel / field_args['bcef_cur']

            #Copy biomass_per_pixel and carbon pools to the temporary feature 
            #for rasterization of the entire layer later
            for field, value in zip(calculated_attribute_names,
                                    [feature_carbon_storage_per_pixel,
                                     biomass_per_pixel, volume_per_pixel]):
                feature.SetField(feature.GetFieldIndex(field), value)

            #This saves the changes made to feature back to the shape layer
            hwp_shape_layer_copy.SetFeature(feature)

    #burn all the attribute values to a raster
    for attribute_name, raster in zip(
                    calculated_attribute_names, [c_hwp, bio_hwp, vol_hwp]):
        raster.GetRasterBand(1).Fill(raster.GetRasterBand(1).GetNoDataValue())
        gdal.RasterizeLayer(raster, [1], hwp_shape_layer_copy,
                                options=['ATTRIBUTE=' + attribute_name])


def calculate_hwp_storage_fut(
    hwp_shapes, base_dataset_uri, c_hwp_uri, bio_hwp_uri, vol_hwp_uri,
    yr_cur, yr_fut):
    """Calculates carbon storage, hwp biomassPerPixel and volumePerPixel due to 
        harvested wood products in parcels on current landscape.
        
        hwp_shapes - a dictionary containing the current and/or future harvest
            maps (or nothing)
            hwp_shapes['cur'] - oal shapefile indicating harvest map from the
                current landscape
            hwp_shapes['fut'] - oal shapefile indicating harvest map from the
                future landscape
        c_hwp - an output GDAL rasterband representing  carbon stored in 
            harvested wood products for current calculation 
        bio_hwp - an output GDAL rasterband representing carbon stored in 
            harvested wood products for land cover under interest
        vol_hwp - an output GDAL rasterband representing carbon stored in
             harvested wood products for land cover under interest
        yr_cur - year of the current landcover map
        yr_fut - year of the current landcover map
        
        No return value"""

    ############### Start
    pixel_area = raster_utils.get_cell_size_from_uri(base_dataset_uri) ** 2 / 10000.0 #convert to Ha
    base_dataset = gdal.Open(base_dataset_uri)
    nodata = -1.0

    c_hwp_cur_uri = raster_utils.temporary_filename()
    bio_hwp_cur_uri = raster_utils.temporary_filename()
    vol_hwp_cur_uri = raster_utils.temporary_filename()

    c_hwp = raster_utils.new_raster_from_base(base_dataset, c_hwp_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)
    bio_hwp = raster_utils.new_raster_from_base(base_dataset, bio_hwp_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)
    vol_hwp = raster_utils.new_raster_from_base(base_dataset, vol_hwp_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)

    #Create a temporary shapefile to hold values of per feature carbon pools
    #HWP biomassPerPixel and volumePerPixel, will be used later to rasterize 
    #those values to output rasters

    calculatedAttributeNames = ['c_hwp_pool', 'bio_hwp', 'vol_hwp']
    if 'cur' in hwp_shapes:
        hwp_shape = ogr.Open(hwp_shapes['cur'])
        hwp_shape_copy = \
            ogr.GetDriverByName('Memory').CopyDataSource(hwp_shape, '')
        hwp_shape_layer_copy = \
            hwp_shape_copy.GetLayer()

        #Create fields in the layers to hold hardwood product pools, 
        #biomassPerPixel and volumePerPixel
        for fieldName in calculatedAttributeNames:
            field_def = ogr.FieldDefn(fieldName, ogr.OFTReal)
            hwp_shape_layer_copy.CreateField(field_def)

        #Visit each feature and calculate the carbon pool, biomassPerPixel, 
        #and volumePerPixel of that parcel
        for feature in hwp_shape_layer_copy:
            #This makes a helpful dictionary to access fields in the feature
            #later in the code
            field_args = _get_fields(feature)

            #If start date and/or the amount of carbon per cut is zero, it 
            #doesn't make sense to do any calculation on carbon pools or 
            #biomassPerPixel/volumePerPixel
            if field_args['start_date'] != 0 and field_args['cut_cur'] != 0:

                time_span = (yr_fut + yr_cur) / 2.0 - field_args['start_date']
                start_years = yr_fut - field_args['start_date']

                #Calculate the carbon pool due to decaying HWP over the 
                #time_span
                feature_carbon_storage_per_pixel = (
                    pixel_area * _carbon_pool_in_hwp_from_parcel(
                        field_args['cut_cur'], time_span, start_years,
                        field_args['freq_cur'], field_args['decay_cur']))

                #Claculate biomassPerPixel and volumePerPixel of harvested wood
                numberOfHarvests = \
                    math.ceil(time_span / float(field_args['freq_cur']))
                #The measure of biomass is in terms of Mg/ha
                biomassInFeaturePerArea = field_args['cut_cur'] * \
                    numberOfHarvests / float(field_args['c_den_cur'])


                biomassPerPixel = biomassInFeaturePerArea * pixel_area
                volumePerPixel = biomassPerPixel / field_args['bcef_cur']

                #Copy biomassPerPixel and carbon pools to the temporary 
                #feature for rasterization of the entire layer later
                for field, value in zip(calculatedAttributeNames,
                                        [feature_carbon_storage_per_pixel,
                                         biomassPerPixel, volumePerPixel]):
                    feature.SetField(feature.GetFieldIndex(field), value)

                #This saves the changes made to feature back to the shape layer
                hwp_shape_layer_copy.SetFeature(feature)

        #burn all the attribute values to a raster
        for attributeName, raster_uri in zip(calculatedAttributeNames,
                                          [c_hwp_cur_uri, bio_hwp_cur_uri, vol_hwp_cur_uri]):
            nodata = -1.e10
            raster = raster_utils.new_raster_from_base(base_dataset, raster_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)
            gdal.RasterizeLayer(raster, [1], hwp_shape_layer_copy, options=['ATTRIBUTE=' + attributeName])
            raster = None

    #handle the future term 
    if 'fut' in hwp_shapes:
        hwp_shape = ogr.Open(hwp_shapes['fut'])
        hwp_shape_copy = \
            ogr.GetDriverByName('Memory').CopyDataSource(hwp_shape, '')
        hwp_shape_layer_copy = \
            hwp_shape_copy.GetLayer()

        #Create fields in the layers to hold hardwood product pools, 
        #biomassPerPixel and volumePerPixel
        for fieldName in calculatedAttributeNames:
            field_def = ogr.FieldDefn(fieldName, ogr.OFTReal)
            hwp_shape_layer_copy.CreateField(field_def)

        #Visit each feature and calculate the carbon pool, biomassPerPixel, 
        #and volumePerPixel of that parcel
        for feature in hwp_shape_layer_copy:
            #This makes a helpful dictionary to access fields in the feature
            #later in the code
            field_args = _get_fields(feature)

            #If start date and/or the amount of carbon per cut is zero, it 
            #doesn't make sense to do any calculation on carbon pools or 
            #biomassPerPixel/volumePerPixel
            if field_args['cut_fut'] != 0:

                time_span = yr_fut - (yr_fut + yr_cur) / 2.0
                start_years = time_span

                #Calculate the carbon pool due to decaying HWP over the 
                #time_span
                feature_carbon_storage_per_pixel = pixel_area * \
                    _carbon_pool_in_hwp_from_parcel(
                    field_args['cut_fut'], time_span, start_years,
                    field_args['freq_fut'], field_args['decay_fut'])

                #Claculate biomassPerPixel and volumePerPixel of harvested wood
                numberOfHarvests = \
                    math.ceil(time_span / float(field_args['freq_fut']))

                biomassInFeaturePerArea = field_args['cut_fut'] * \
                    numberOfHarvests / float(field_args['c_den_fut'])

                biomassPerPixel = biomassInFeaturePerArea * pixel_area

                volumePerPixel = biomassPerPixel / field_args['bcef_fut']

                #Copy biomassPerPixel and carbon pools to the temporary 
                #feature for rasterization of the entire layer later
                for field, value in zip(calculatedAttributeNames,
                                        [feature_carbon_storage_per_pixel,
                                         biomassPerPixel, volumePerPixel]):
                    feature.SetField(feature.GetFieldIndex(field), value)

                #This saves the changes made to feature back to the shape layer
                hwp_shape_layer_copy.SetFeature(feature)

        #burn all the attribute values to a raster
        for attributeName, (raster_uri, cur_raster_uri) in zip(
            calculatedAttributeNames, [(c_hwp_uri, c_hwp_cur_uri), (bio_hwp_uri, bio_hwp_cur_uri), (vol_hwp_uri, vol_hwp_cur_uri)]):

            #Burn the future data on to a raster
            cur_raster = gdal.Open(cur_raster_uri)
            temp_filename = raster_utils.temporary_filename()
            temp_raster = raster_utils.new_raster_from_base(
                cur_raster, temp_filename, 'GTiff',
                nodata, gdal.GDT_Float32, fill_value=nodata)
            gdal.RasterizeLayer(temp_raster, [1], hwp_shape_layer_copy,
                                options=['ATTRIBUTE=' + attributeName])
            temp_raster = None
            cur_raster = None


            #add temp_raster and raster cur raster into the output raster
            nodata = -1.0e10
            base_nodata = raster_utils.get_nodata_from_uri(raster_uri)
            cur_nodata = raster_utils.get_nodata_from_uri(cur_raster_uri)
            def add_op(base, current):
                if base == base_nodata or current == cur_nodata:
                    return nodata
                return base + current

            pixel_size_out = raster_utils.get_cell_size_from_uri(raster_uri)
            raster_utils.vectorize_datasets(
                [cur_raster_uri, temp_filename], add_op, raster_uri, gdal.GDT_Float32, nodata,
                pixel_size_out, "intersection", dataset_to_align_index=0)





def _get_fields(feature):
    """Return a dict with all fields in the given feature.

        feature - an OGR feature.

        Returns an assembled python dict with a mapping of 
        fieldname -> fieldvalue"""

    fields = {}
    for i in xrange(feature.GetFieldCount()):
        field_def = feature.GetFieldDefnRef(i)
        name = field_def.GetName().lower()
        value = feature.GetField(i)
        fields[name] = value

    return fields


def _carbon_pool_in_hwp_from_parcel(carbonPerCut, start_years, timeSpan, harvestFreq,
                              decay):
    """This is the summation equation that appears in equations 1, 5, 6, and 7
        from the user's guide

        carbonPerCut - The amount of carbon removed from a parcel during a
            harvest period
        start_years - The number of years ago that the harvest first started
        timeSpan - The number of years to calculate the harvest over
        harvestFreq - How many years between harvests
        decay - the rate at which carbon is decaying from HWP harvested from
            parcels

        returns a float indicating the amount of carbon stored from HWP
            harvested in units of Mg/ha"""

    carbonSum = 0.0
    omega = math.log(2) / decay
    #Recall that xrange is nonexclusive on the upper bound, so it corresponds
    #to the -1 in the summation terms given in the user's manual
    for t in xrange(int(math.ceil(start_years / harvestFreq))):
        carbonSum += (1 - math.exp(-omega)) / (omega *
            math.exp((timeSpan - t * harvestFreq) * omega))
    return carbonSum * carbonPerCut






#This part is for command line invocation and allows json objects to be passed
#as the argument dictionary
if __name__ == '__main__':
    modulename, json_args = sys.argv
    args = json.loads(json_args)
    execute(args)
