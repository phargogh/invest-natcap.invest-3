"""InVEST Carbon biophysical module at the "uri" level"""

import os
import math
import logging
import shutil

from osgeo import gdal
from osgeo import ogr

from invest_natcap import raster_utils
from invest_natcap.carbon import carbon_utils

logging.basicConfig(format='%(asctime)s %(name)-18s %(levelname)-8s \
    %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

LOGGER = logging.getLogger('carbon_biophysical')

def execute(args):
    return execute_30(**args)

def execute_30(**args):
    """This function invokes the carbon model given URI inputs of files.
        It will do filehandling and open/create appropriate objects to
        pass to the core carbon biophysical processing function.  It may write
        log, warning, or error messages to stdout.

        args - a python dictionary with at the following possible entries:
        args['workspace_dir'] - a uri to the directory that will write output
            and other temporary files during calculation. (required)
        args['suffix'] - a string to append to any output file name (optional)
        args['lulc_cur_uri'] - is a uri to a GDAL raster dataset (required)
        args['carbon_pools_uri'] - is a uri to a CSV or DBF dataset mapping carbon
            storage density to the lulc classifications specified in the
            lulc rasters. (required if 'do_uncertainty' is false)
        args['carbon_pools_uncertain_uri'] - as above, but has probability distribution
            data for each lulc type rather than point estimates.
            (required if 'do_uncertainty' is true)
        args['do_uncertainty'] - a boolean that indicates whether we should do
            uncertainty analysis. Defaults to False if not present.
        args['confidence_threshold'] - a number between 0 and 100 that indicates
            the minimum threshold for which we should highlight regions in the output
            raster. (required if 'do_uncertainty' is True)
        args['lulc_fut_uri'] - is a uri to a GDAL raster dataset (optional
         if calculating sequestration)
        args['lulc_cur_year'] - An integer representing the year of lulc_cur
            used in HWP calculation (required if args contains a
            'hwp_cur_shape_uri', or 'hwp_fut_shape_uri' key)
        args['lulc_fut_year'] - An integer representing the year of  lulc_fut
            used in HWP calculation (required if args contains a
            'hwp_fut_shape_uri' key)
        args['lulc_redd_uri'] - is a uri to a GDAL raster dataset that represents
            land cover data for the REDD policy scenario (optional).
        args['hwp_cur_shape_uri'] - Current shapefile uri for harvested wood
            calculation (optional, include if calculating current lulc hwp)
        args['hwp_fut_shape_uri'] - Future shapefile uri for harvested wood
            calculation (optional, include if calculating future lulc hwp)

        returns a dict with the names of all output files."""

    file_suffix = carbon_utils.make_suffix(args)
    dirs = carbon_utils.setup_dirs(args['workspace_dir'],
                                   'output', 'intermediate')

    def outfile_uri(prefix, scenario_type, dirtype='output', filetype='tif'):
        '''Creates the appropriate output file URI.

           prefix: 'tot_C', 'sequest', or similar
           scenario type: 'cur', 'fut', or 'redd'
           dirtype: 'output' or 'intermediate'
           '''
        if scenario_type == 'fut' and args.get('lulc_redd_uri'):
            # We're doing REDD analysis, so call the future scenario 'base',
            # since it's the 'baseline' scenario.
            scenario_type = 'base'

        filename = '%s_%s%s.%s' % (prefix, scenario_type, file_suffix, filetype)
        return os.path.join(dirs[dirtype], filename)

    #1) load carbon pools into dictionary indexed by LULC
    do_uncertainty = args.get('do_uncertainty', False)
    if do_uncertainty:
        pools = raster_utils.get_lookup_from_table(args['carbon_pools_uncertain_uri'], 'lucode')
    else:
        pools = raster_utils.get_lookup_from_table(args['carbon_pools_uri'], 'lucode')

    #2) map lulc_cur and _fut (if availble) to total carbon
    outputs = {}
    for lulc_uri in ['lulc_cur_uri', 'lulc_fut_uri', 'lulc_redd_uri']:
        if lulc_uri in args:
            scenario_type = lulc_uri.split('_')[-2] #get the 'cur' or 'fut'

            populate_carbon_pools(
                pools, do_uncertainty, args[lulc_uri], scenario_type)

            nodata = raster_utils.get_nodata_from_uri(args[lulc_uri])
            nodata_out = -5.0
            def map_carbon_pool(lulc):
                if lulc == nodata:
                    return nodata_out
                return pools[lulc]['total_%s' % scenario_type]
            dataset_out_uri = outfile_uri('tot_C', scenario_type)
            outputs['tot_C_%s' % scenario_type] = dataset_out_uri

            pixel_size_out = raster_utils.get_cell_size_from_uri(args[lulc_uri])
            # Create a raster that models total carbon storage per pixel.
            raster_utils.vectorize_datasets(
                [args[lulc_uri]], map_carbon_pool, dataset_out_uri,
                gdal.GDT_Float32, nodata_out, pixel_size_out,
                "intersection", dataset_to_align_index=0)

            if do_uncertainty:
                def map_carbon_pool_variance(lulc):
                    if lulc == nodata:
                        return nodata_out
                    return pools[lulc]['variance_%s' % scenario_type]
                variance_out_uri = outfile_uri(
                    'variance_C', scenario_type, dirtype='intermediate')
                outputs['variance_C_%s' % scenario_type] = variance_out_uri

                # Create a raster that models variance in carbon storage per pixel.
                raster_utils.vectorize_datasets(
                    [args[lulc_uri]], map_carbon_pool_variance, variance_out_uri,
                    gdal.GDT_Float32, nodata_out, pixel_size_out,
                    "intersection", dataset_to_align_index=0)

            #Add calculate the hwp storage, if it is passed as an input argument
            hwp_key = 'hwp_%s_shape_uri' % scenario_type
            if hwp_key in args:
                c_hwp_uri = outfile_uri('c_hwp', scenario_type, dirtype='intermediate')
                bio_hwp_uri = outfile_uri('bio_hwp', scenario_type, dirtype='intermediate')
                vol_hwp_uri = outfile_uri('vol_hwp', scenario_type, dirtype='intermediate')

                if scenario_type == 'cur':
                    calculate_hwp_storage_cur(
                        args[hwp_key], args[lulc_uri], c_hwp_uri, bio_hwp_uri,
                        vol_hwp_uri, args['lulc_%s_year' % scenario_type])
                    #TODO add to tot_C_cur
                    temp_c_cur_uri = raster_utils.temporary_filename()
                    LOGGER.debug(outputs)
                    shutil.copyfile(outputs['tot_C_cur'], temp_c_cur_uri)

                    hwp_cur_nodata = raster_utils.get_nodata_from_uri(c_hwp_uri)
                    def add_op(tmp_c_cur, hwp_cur):
                        if hwp_cur == hwp_cur_nodata:
                            return tmp_c_cur
                        return tmp_c_cur + hwp_cur

                    raster_utils.vectorize_datasets(
                        [temp_c_cur_uri, c_hwp_uri], add_op, outputs['tot_C_cur'], gdal.GDT_Float32, nodata_out,
                        pixel_size_out, "intersection", dataset_to_align_index=0)

                elif scenario_type == 'fut':
                    hwp_shapes = {}

                    if 'hwp_cur_shape_uri' in args:
                        hwp_shapes['cur'] = args['hwp_cur_shape_uri']
                    if 'hwp_fut_shape_uri' in args:
                        hwp_shapes['fut'] = args['hwp_fut_shape_uri']

                    calculate_hwp_storage_fut(
                        hwp_shapes, args[lulc_uri], c_hwp_uri, bio_hwp_uri,
                        vol_hwp_uri, args['lulc_cur_year'], args['lulc_fut_year'])

                    #TODO add to tot_C_cur
                    temp_c_fut_uri = raster_utils.temporary_filename()
                    LOGGER.debug(outputs)
                    shutil.copyfile(outputs['tot_C_fut'], temp_c_fut_uri)

                    hwp_fut_nodata = raster_utils.get_nodata_from_uri(c_hwp_uri)
                    def add_op(tmp_c_fut, hwp_fut):
                        if hwp_fut == hwp_fut_nodata:
                            return tmp_c_fut
                        return tmp_c_fut + hwp_fut

                    raster_utils.vectorize_datasets(
                        [temp_c_fut_uri, c_hwp_uri], add_op, outputs['tot_C_fut'], gdal.GDT_Float32, nodata_out,
                        pixel_size_out, "intersection", dataset_to_align_index=0)


    #TODO: sequestration
    for fut_type in ['fut', 'redd']:
        fut_type_lulc_uri = 'lulc_%s_uri' % fut_type
        if 'lulc_cur_uri' in args and fut_type_lulc_uri in args:
            def sub_op(c_cur, c_fut):
                if nodata_out in [c_cur, c_fut]:
                    return nodata_out
                return c_fut - c_cur

            pixel_size_out = raster_utils.get_cell_size_from_uri(args['lulc_cur_uri'])
            outputs['sequest_%s' % fut_type] = outfile_uri('sequest', fut_type)
            raster_utils.vectorize_datasets(
                [outputs['tot_C_cur'], outputs['tot_C_%s' % fut_type]], sub_op,
                outputs['sequest_%s' % fut_type], gdal.GDT_Float32, nodata_out,
                pixel_size_out, "intersection", dataset_to_align_index=0)

            if do_uncertainty:
                confidence_threshold = args['confidence_threshold']

                # Returns 1 if we're confident storage will increase,
                #         -1 if we're confident storage will decrease,
                #         0 if we're not confident either way.
                def confidence_op(c_cur, c_fut, var_cur, var_fut):
                    if nodata_out in [c_cur, c_fut, var_cur, var_fut]:
                        return nodata_out

                    if var_cur == 0 and var_fut == 0:
                        # There's no variance, so we can just compare the mean estimates.
                        if c_fut > c_cur:
                            return 1
                        if c_fut < c_cur:
                            return -1
                        return 0

                    # Given two distributions (one for current storage, one for future storage),
                    # we use the difference distribution (current storage - future storage),
                    # and calculate the probability that the difference is less than 0.
                    # This is equal to the probability that the future storage is greater than
                    # the current storage.
                    # We calculate the standard score by beginning with 0, subtracting the mean
                    # of the difference distribution, and dividing by the standard deviation
                    # of the difference distribution.
                    # The mean of the difference distribution is the difference of the means of cur and fut.
                    # The variance of the difference distribution is the sum of the variances of cur and fut.
                    standard_score = (c_fut - c_cur) / math.sqrt(var_cur + var_fut)

                    # Calculate the cumulative distribution function for the standard normal distribution.
                    # This gives us the probability that future carbon storage is greater than
                    # current carbon storage.
                    # This formula is copied from http://docs.python.org/3.2/library/math.html
                    probability = (1.0 + math.erf(standard_score / math.sqrt(2.0))) / 2.0

                    # Multiply by 100 so we have probability in the same units as the confidence_threshold.
                    confidence = 100 * probability
                    if confidence >= confidence_threshold:
                        # We're confident carbon storage will increase.
                        return 1
                    if confidence <= 100 - confidence_threshold:
                        # We're confident carbon storage will decrease.
                        return -1
                    # We're not confident about whether storage will increase or decrease.
                    return 0

                outputs['conf_%s' % fut_type] = outfile_uri('conf', fut_type)
                raster_utils.vectorize_datasets(
                    [outputs[name] for name in ['tot_C_cur', 'tot_C_%s' % fut_type,
                                                       'variance_C_cur', 'variance_C_%s' % fut_type]],
                    confidence_op, outputs['conf_%s' % fut_type], gdal.GDT_Float32, nodata_out,
                    pixel_size_out, "intersection", dataset_to_align_index=0)

    return outputs


def populate_carbon_pools(pools, do_uncertainty, lulc_uri, scenario_type):
    """Populates pools with data on carbon content per LULC type."""

    cell_area_ha = (
        raster_utils.get_cell_area_from_uri(lulc_uri) / 10000.0)

    pool_estimate_types = ['c_above', 'c_below', 'c_soil', 'c_dead']

    if do_uncertainty:
        # We want the mean and standard deviation columns.
        pool_estimate_sds = [s + '_sd' for s in pool_estimate_types]
        pool_estimate_types = [s + '_mean' for s in pool_estimate_types]

    for lulc_id in pools:
        # Compute the total carbon per pixel for each lulc type
        pools[lulc_id]['total_%s' % scenario_type] = cell_area_ha * sum(
            [pools[lulc_id][pool_type] for pool_type in pool_estimate_types])

        if do_uncertainty:
            # Compute the total variance per pixel for each lulc type.
            # We have a normal distribution for each pool; we assume each is
            # independent, so the variance of the sum is equal to the sum of
            # the variances. Note that we scale by the area squared.
            pools[lulc_id]['variance_%s' % scenario_type] = (
                (cell_area_ha ** 2) * sum(
                    [pools[lulc_id][pool_type_sd] ** 2
                     for pool_type_sd in pool_estimate_sds]))


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
    nodata = -5.0

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
    for attribute_name, raster_uri in zip(
        calculated_attribute_names, [c_hwp_uri, bio_hwp_uri, vol_hwp_uri]):

        raster = raster_utils.new_raster_from_base(
            base_dataset, raster_uri, 'GTiff', nodata, gdal.GDT_Float32,
            fill_value=nodata)
        gdal.RasterizeLayer(raster, [1], hwp_shape_layer_copy,
                            options=['ATTRIBUTE=' + attribute_name])
        raster.FlushCache()
        raster = None


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
    nodata = -5.0

    c_hwp_cur_uri = raster_utils.temporary_filename()
    bio_hwp_cur_uri = raster_utils.temporary_filename()
    vol_hwp_cur_uri = raster_utils.temporary_filename()

    raster_utils.new_raster_from_base_uri(base_dataset_uri, c_hwp_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)
    raster_utils.new_raster_from_base_uri(base_dataset_uri, bio_hwp_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)
    raster_utils.new_raster_from_base_uri(base_dataset_uri, vol_hwp_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)

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
            nodata = -1.0
            raster_utils.new_raster_from_base_uri(base_dataset_uri, raster_uri, 'GTiff', nodata, gdal.GDT_Float32, fill_value=nodata)
            raster = gdal.Open(raster_uri, gdal.GA_Update)
            gdal.RasterizeLayer(raster, [1], hwp_shape_layer_copy, options=['ATTRIBUTE=' + attributeName])
            raster.FlushCache()
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

            temp_filename = raster_utils.temporary_filename()
            raster_utils.new_raster_from_base_uri(
                base_dataset_uri, temp_filename, 'GTiff',
                nodata, gdal.GDT_Float32, fill_value=nodata)
            temp_raster = gdal.Open(temp_filename, gdal.GA_Update)
            gdal.RasterizeLayer(temp_raster, [1], hwp_shape_layer_copy,
                                options=['ATTRIBUTE=' + attributeName])
            temp_raster.FlushCache()
            temp_raster = None

            #add temp_raster and raster cur raster into the output raster
            nodata = -1.0
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
