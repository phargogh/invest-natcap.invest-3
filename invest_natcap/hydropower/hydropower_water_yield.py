"""Module that contains the core computational components for the hydropower
    model including the water yield, water scarcity, and valuation functions"""

import logging
import os
import csv
import math

import numpy as np
from osgeo import gdal
from osgeo import ogr

from invest_natcap import raster_utils
import hydropower_cython_core

LOGGER = logging.getLogger('hydropower_core')

def execute(args):
    """Executes the water_yield model
        
        args - a python dictionary with at least the following possible entries:
    
        args['workspace_dir'] - a uri to the directory that will write output
            and other temporary files during calculation. (required)
        
        args['lulc_uri'] - a uri to a land use/land cover raster whose
            LULC indexes correspond to indexes in the biophysical table input.
            Used for determining soil retention and other biophysical 
            properties of the landscape. (required)
        
        args['soil_depth_uri'] - a uri to an input raster describing the 
            average soil depth value for each cell (mm) (required)
        
        args['precipitation_uri'] - a uri to an input raster describing the 
            average annual precipitation value for each cell (mm) (required)
        
        args['pawc_uri'] - a uri to an input raster describing the 
            plant available water content value for each cell. Plant Available
            Water Content fraction (PAWC) is the fraction of water that can be
            stored in the soil profile that is available for plants' use. 
            PAWC is a fraction from 0 to 1 (required)
        
        args['eto_uri'] - a uri to an input raster describing the 
            annual average evapotranspiration value for each cell. Potential
            evapotranspiration is the potential loss of water from soil by
            both evaporation from the soil and transpiration by healthy Alfalfa
            (or grass) if sufficient water is available (mm) (required)
        
        args['watersheds_uri'] - a uri to an input shapefile of the watersheds
            of interest as polygons. (required)
        
        args['sub_watersheds_uri'] - a uri to an input shapefile of the 
            subwatersheds of interest that are contained in the
            'watersheds_uri' shape provided as input. (required)
        
        args['biophysical_table_uri'] - a uri to an input CSV table of 
            land use/land cover classes, containing data on biophysical 
            coefficients such as root_depth (mm) and etk, which are required. 
            NOTE: these data are attributes of each LULC class rather than 
            attributes of individual cells in the raster map (required)
        
        args['seasonality_constant'] - floating point value between 1 and 10 
            corresponding to the seasonal distribution of precipitation 
            (required)
        
        args['results_suffix'] - a string that will be concatenated onto the
           end of file names (optional)
           
        returns - nothing"""
        
    LOGGER.info('Starting Water Yield Core Calculations')

    # Construct folder paths
    workspace = args['workspace_dir']
    intermediate_dir = os.path.join(workspace, 'intermediate')
    output_dir = os.path.join(workspace, 'output')
    service_dir = os.path.join(workspace, 'service')
    pixel_dir = os.path.join(output_dir, 'pixel')
    raster_utils.create_directories(
            [intermediate_dir, output_dir, service_dir, pixel_dir])
    
    # Get inputs from the args dictionary
    lulc_uri = args['lulc_uri']
    eto_uri = args['eto_uri']
    precip_uri = args['precipitation_uri']
    soil_depth_uri = args['soil_depth_uri']
    pawc_uri = args['pawc_uri']
    sub_sheds_uri = args['sub_watersheds_uri']
    sheds_uri = args['watersheds_uri']
    seasonality_constant = float(args['seasonality_constant'])
    
    # Open/read in the csv file into a dictionary and add to arguments
    biophysical_table_map = {}
    biophysical_table_file = open(args['biophysical_table_uri'])
    reader = csv.DictReader(biophysical_table_file)
    for row in reader:
        biophysical_table_map[int(row['lucode'])] = \
            {'etk':float(row['etk']), 'root_depth':float(row['root_depth'])}

    biophysical_table_file.close() 
    bio_dict = biophysical_table_map 
    
    # Append a _ to the suffix if it's not empty and doens't already have one
    try:
        file_suffix = args['suffix']
        if file_suffix != "" and not file_suffix.startswith('_'):
            file_suffix = '_' + file_suffix
    except KeyError:
        file_suffix = ''
    
    # Paths for clipping the fractp/wyield raster to watershed polygons
    fractp_clipped_path = os.path.join(pixel_dir, 'fractp%s.tif' % file_suffix)
    wyield_clipped_path = os.path.join(pixel_dir, 'wyield%s.tif' % file_suffix)
    
    # Paths for the actual evapotranspiration rasters
    aet_path = os.path.join(pixel_dir, 'aet%s.tif' % file_suffix) 
    
    # Paths for the watershed and subwatershed tables
    shed_table_path = os.path.join(output_dir, 'water_yield_watershed.csv') 
    sub_table_path = os.path.join(output_dir, 'water_yield_subwatershed.csv') 
    
    # The nodata value that will be used for created output rasters
    #out_nodata = np.finfo(np.float32).min + 1.0
    out_nodata = - 1.0
    
    # Break the bio_dict into two separate dictionaries based on
    # etk and root_depth fields to use for reclassifying 
    etk_dict = {}
    root_dict = {}
    for lulc_code in bio_dict:
        etk_dict[lulc_code] = bio_dict[lulc_code]['etk']
        root_dict[lulc_code] = bio_dict[lulc_code]['root_depth']

    # Create etk raster from table values to use in future calculations
    LOGGER.info("Reclassifying temp_etk raster")
    tmp_etk_raster_uri = raster_utils.temporary_filename()
    
    raster_utils.reclassify_dataset_uri(
            lulc_uri, etk_dict, tmp_etk_raster_uri, gdal.GDT_Float32,
            out_nodata)

    # Create root raster from table values to use in future calculations
    LOGGER.info("Reclassifying tmp_root raster")
    tmp_root_raster_uri = raster_utils.temporary_filename()
    
    raster_utils.reclassify_dataset_uri(
            lulc_uri, root_dict, tmp_root_raster_uri, gdal.GDT_Float32,
            out_nodata)

    # Get out_nodata values so that we can avoid any issues when running
    # operations
    etk_nodata = raster_utils.get_nodata_from_uri(tmp_etk_raster_uri)
    root_nodata = raster_utils.get_nodata_from_uri(tmp_root_raster_uri)
    precip_nodata = raster_utils.get_nodata_from_uri(precip_uri)
    eto_nodata = raster_utils.get_nodata_from_uri(eto_uri)
    soil_depth_nodata = raster_utils.get_nodata_from_uri(soil_depth_uri)
    pawc_nodata = raster_utils.get_nodata_from_uri(pawc_uri)
    
    # Dictionary of out_nodata values corresponding to values for fractp_op that 
    # will help avoid any out_nodata calculation issues
    fractp_nodata_dict = {'etk':etk_nodata, 
                          'root':root_nodata,
                          'precip':precip_nodata,
                          'eto':eto_nodata,
                          'soil':soil_depth_nodata,
                          'pawc':pawc_nodata}
    
    def fractp_op(etk, eto, precip, root, soil, pawc):
        """A wrapper function to call hydropower's cython core. Acts as a
            closure for fractp_nodata_dict, out_nodata, seasonality_constant
            """

        return hydropower_cython_core.fractp_op(
            fractp_nodata_dict, out_nodata, seasonality_constant, etk,
            eto, precip, root, soil, pawc)
    
    # Vectorize operation
    fractp_vec = np.vectorize(fractp_op)
    
    # Get pixel size from tmp_etk_raster_uri which should be the same resolution
    # as LULC raster
    pixel_size = raster_utils.get_cell_size_from_uri(tmp_etk_raster_uri)

    raster_list = [
            tmp_etk_raster_uri, eto_uri, precip_uri, tmp_root_raster_uri,
            soil_depth_uri, pawc_uri]
    
    # Create clipped fractp_clipped raster
    raster_utils.vectorize_datasets(
            raster_list, fractp_vec, fractp_clipped_path, gdal.GDT_Float32,
            out_nodata, pixel_size, 'intersection', aoi_uri=sub_sheds_uri)
    
    LOGGER.debug('Performing wyield operation')
    
    def wyield_op(fractp, precip):
        """Function that calculates the water yeild raster
        
           fractp - numpy array with the fractp raster values
           precip - numpy array with the precipitation raster values (mm)
           
           returns - water yield value (mm)"""
        
        if fractp == out_nodata or precip == precip_nodata:
            return out_nodata
        else:
            return (1.0 - fractp) * precip
    
    # Create clipped wyield_clipped raster
    raster_utils.vectorize_datasets(
            [fractp_clipped_path, precip_uri], wyield_op, wyield_clipped_path,
            gdal.GDT_Float32, out_nodata, pixel_size, 'intersection',
            aoi_uri=sub_sheds_uri)

    # Making a copy of watershed and sub-watershed to add water yield outputs
    # to
    sub_sheds_out_uri = os.path.join(output_dir, 'sub_sheds.shp')
    sheds_out_uri = os.path.join(output_dir, 'sheds.shp')
    raster_utils.copy_datasource_uri(sub_sheds_uri, sub_sheds_out_uri)
    raster_utils.copy_datasource_uri(sheds_uri, sheds_out_uri)

    def aet_op(fractp, precip):
        """Function to compute the actual evapotranspiration values
        
            fractp - numpy array with the fractp raster values
            precip - numpy array with the precipitation raster values (mm)
            
            returns - actual evapotranspiration values (mm)"""
        
        # checking if fractp >= 0 because it's a value that's between 0 and 1
        # and the nodata value is a large negative number. 
        if fractp >= 0 and precip != precip_nodata:
            return fractp * precip
        else:
            return out_nodata
    
    LOGGER.debug('Performing aet operation')
    # Create clipped aet raster 
    raster_utils.vectorize_datasets(
            [fractp_clipped_path, precip_uri], aet_op, aet_path,
            gdal.GDT_Float32, out_nodata, pixel_size, 'intersection',
            aoi_uri=sub_sheds_uri)
   
    # Create a list of tuples that pair up field names and raster uris so that
    # we can nicely do operations below
    sws_tuple_names_uris = [
            ('precip_mn', precip_uri),('PET_mn', eto_uri),
            ('AET_mn', aet_path),('wyield_mn', wyield_clipped_path),
            ('fractp_mn', fractp_clipped_path)]
   
    for key_name, rast_uri in sws_tuple_names_uris:
        # Aggregrate mean over the sub-watersheds for each uri listed in
        # 'sws_tuple_names_uri'
        key_dict = raster_utils.aggregate_raster_values_uri(
                rast_uri, sub_sheds_uri, 'subws_id', 'mean')
        # Add aggregated values to sub-watershed shapefile under new field
        # 'key_name'
        add_dict_to_shape(sub_sheds_out_uri, key_dict, key_name, 'subws_id')
  
    # Aggregate the water yield by summing pixels over sub-watersheds
    wyield_sum_dict = raster_utils.aggregate_raster_values_uri(
            wyield_clipped_path, sub_sheds_uri, 'subws_id', 'sum')
    
    # Add aggregated water yield sums to sub-watershed shapefile
    add_dict_to_shape(
            sub_sheds_out_uri, wyield_sum_dict, 'wyield_sum', 'subws_id')
    
    # Compute the water yield volume and water yield volume per hectare. The
    # values per sub-watershed will be added as fields in the sub-watersheds
    # shapefile
    compute_water_yield_volume(sub_sheds_out_uri)
    
    # Create a dictionary that maps watersheds to sub-watersheds given the
    # watershed and sub-watershed shapefiles
    wsr = sheds_map_subsheds(sheds_uri, sub_sheds_uri)
    LOGGER.debug('wsr : %s', wsr)
    
    # Create a dictionary that maps sub-watersheds to watersheds
    sws_dict = {}
    for key, val in wsr.iteritems():
        sws_dict[key] = val
    
    LOGGER.debug('sws_dict : %s', sws_dict)
   
    # Add the corresponding watershed ids to the sub-watershed shapefile as a
    # new field
    add_dict_to_shape(sub_sheds_out_uri, sws_dict, 'ws_id', 'subws_id')
    
    # List of wanted fields to output in the sub-watershed CSV table
    sub_field_list = [
            'ws_id', 'subws_id', 'precip_mn', 'PET_mn', 'AET_mn', 
            'wyield_mn', 'wyield_sum', 'wyield_vol']
    
    # Get a dictionary from the sub-watershed shapefiles attributes based on the
    # fields to be outputted to the CSV table
    sub_value_dict = extract_datasource_table_by_key(
            sub_sheds_out_uri, 'subws_id', sub_field_list)
    
    LOGGER.debug('sub_value_dict : %s', sub_value_dict)
    
    # Write sub-watershed CSV table
    write_new_table(sub_table_path, sub_field_list, sub_value_dict)
    
    # Create a list of tuples that pair up field names and raster uris so that
    # we can nicely do operations below
    ws_tuple_names_uris = [
            ('precip_mn', precip_uri),('PET_mn', eto_uri),
            ('AET_mn', aet_path),('wyield_mn', wyield_clipped_path)]
   
    for key_name, rast_uri in ws_tuple_names_uris:
        # Aggregrate mean over the watersheds for each uri listed in
        # 'ws_tuple_names_uri'
        key_dict = raster_utils.aggregate_raster_values_uri(
                rast_uri, sheds_uri, 'ws_id', 'mean')
        # Add aggregated values to watershed shapefile under new field
        # 'key_name'
        add_dict_to_shape(sheds_out_uri, key_dict, key_name, 'ws_id')

    # Aggregate the water yield by summing pixels over the watersheds
    wyield_sum_dict = raster_utils.aggregate_raster_values_uri(
            wyield_clipped_path, sheds_uri, 'ws_id', 'sum')
        
    # Add aggregated water yield sums to watershed shapefile
    add_dict_to_shape(sheds_out_uri, wyield_sum_dict, 'wyield_sum', 'ws_id')
    
    compute_water_yield_volume(sheds_out_uri)
    
    # List of wanted fields to output in the watershed CSV table
    field_list = [
            'ws_id', 'precip_mn', 'PET_mn', 'AET_mn', 'wyield_mn', 'wyield_sum',
            'wyield_vol']
    
    # Get a dictionary from the watershed shapefiles attributes based on the
    # fields to be outputted to the CSV table
    value_dict = extract_datasource_table_by_key(
            sheds_out_uri, 'ws_id', field_list)
    
    LOGGER.debug('value_dict : %s', value_dict)
    
    # Write watershed CSV table
    write_new_table(shed_table_path, field_list, value_dict)
   
    water_scarcity_checked = args.pop('water_scarcity_container', False)
    if not water_scarcity_checked:
        LOGGER.debug('Water Scarcity Not Selected')
        # The rest of the function is water scarcity and valuation, so we can
        # quit now
        return

    """Executes the water scarcity model
        
        args['demand_table'] - a dictionary of LULC classes,
            showing consumptive water use for each landuse / land-cover type
            (required)
        args['hydro_calibration_table'] - a dictionary of 
            hydropower stations with associated calibration values (required)
        
        returns nothing"""

    LOGGER.info('Starting Water Scarcity Core Calculations')
    
    # Paths for watershed and sub watershed scarcity tables
    scarcity_table_ws_uri = os.path.join(
            output_dir, 'water_scarcity_watershed.csv') 
    scarcity_table_sws_uri = os.path.join(
            output_dir, 'water_scarcity_subwatershed.csv') 
    
    #Open/read in the csv files into a dictionary and add to arguments
    demand_dict = {}
    demand_table_file = open(args['demand_table_uri'])
    reader = csv.DictReader(demand_table_file)
    for row in reader:
        demand_dict[int(row['lucode'])] = int(row['demand'])
    
    LOGGER.debug('Demand_Dict : %s', demand_dict)
    demand_table_file.close()
    
    calib_dict = {}
    hydro_cal_table_file = open(args['hydro_calibration_table_uri'])
    reader = csv.DictReader(hydro_cal_table_file)
    for row in reader:
        calib_dict[int(row['ws_id'])] = float(row['calib'])

    LOGGER.debug('Calib_Dict : %s', calib_dict) 
    hydro_cal_table_file.close()
    
    # Making a copy of watershed and sub-watershed to add water yield outputs
    # to
    scarcity_sub_sheds_uri = os.path.join(output_dir, 'scarcity_sub_sheds.shp')
    scarcity_sheds_uri = os.path.join(output_dir, 'scarcity_sheds.shp')
    raster_utils.copy_datasource_uri(sub_sheds_uri, scarcity_sub_sheds_uri)
    raster_utils.copy_datasource_uri(sheds_uri, scarcity_sheds_uri)
    
    calculate_cyield_vol(sub_sheds_out_uri, calib_dict, scarcity_sub_sheds_uri)
    calculate_cyield_vol(sheds_out_uri, calib_dict, scarcity_sheds_uri)
    
    # Create demand raster from table values to use in future calculations
    LOGGER.info("Reclassifying demand raster")
    tmp_demand_uri = raster_utils.temporary_filename()
    
    raster_utils.reclassify_dataset_uri(
            lulc_uri, demand_dict, tmp_demand_uri, gdal.GDT_Float32,
            out_nodata)

    LOGGER.info('Creating consump_vol raster')

    demand_sum_dict_sws = raster_utils.aggregate_raster_values_uri(
            tmp_demand_uri, sub_sheds_uri, 'subws_id', 'sum') 
    
    demand_sum_dict_ws = raster_utils.aggregate_raster_values_uri(
            tmp_demand_uri, sheds_uri, 'ws_id', 'sum') 
    
    # Add aggregated
    add_dict_to_shape(
            scarcity_sub_sheds_uri, demand_sum_dict_sws, 'consum_vol', 'subws_id')
    
    add_dict_to_shape(
            scarcity_sheds_uri, demand_sum_dict_ws, 'consum_vol', 'ws_id')
    
    LOGGER.debug('Demand_Sum_Dict : %s', demand_sum_dict_sws)
    
    LOGGER.info('Creating consump_mn raster')
    demand_mn_dict_sws = raster_utils.aggregate_raster_values_uri(
            tmp_demand_uri, sub_sheds_uri, 'subws_id', 'mean',
            ignore_nodata=False)    
    
    demand_mn_dict_ws = raster_utils.aggregate_raster_values_uri(
            tmp_demand_uri, sheds_uri, 'ws_id', 'mean')    
    
    # Add aggregated water yield sums to watershed shapefile
    add_dict_to_shape(
            scarcity_sub_sheds_uri, demand_mn_dict_sws, 'consum_mn', 'subws_id')
    
    add_dict_to_shape(
            scarcity_sheds_uri, demand_mn_dict_ws, 'consum_mn', 'ws_id')
    
    LOGGER.debug('mean_dict : %s', demand_mn_dict_sws)

    compute_rsupply_volume(scarcity_sub_sheds_uri, sub_sheds_out_uri)
    compute_rsupply_volume(scarcity_sheds_uri, sheds_out_uri)
    
    # Add the corresponding watershed ids to the sub-watershed shapefile as a
    # new field
    add_dict_to_shape(scarcity_sub_sheds_uri, sws_dict, 'ws_id', 'subws_id')
    
    # List of wanted fields to output in the sub-watershed CSV table
    scarcity_field_list_sws = [
            'ws_id', 'subws_id', 'cyield_vol', 'consum_vol', 'consum_mn', 
            'rsupply_vl', 'rsupply_mn']
    
    sub_field_list = sub_field_list + scarcity_field_list_sws[2:]

    # Get a dictionary from the sub-watershed shapefiles attributes based on the
    # fields to be outputted to the CSV table
    scarcity_sub_value_dict = extract_datasource_table_by_key(
            scarcity_sub_sheds_uri, 'subws_id', scarcity_field_list_sws)
   
    scarcity_dict_sws = combine_dictionaries(
            sub_value_dict, scarcity_sub_value_dict)

    LOGGER.debug('Scarcity_dict_sws : %s', scarcity_dict_sws)
    
    # Write sub-watershed CSV table
    write_new_table(scarcity_table_sws_uri, sub_field_list, scarcity_dict_sws)
    
    scarcity_field_list_ws = [
            'ws_id', 'cyield_vol', 'consum_vol', 'consum_mn', 'rsupply_vl',
            'rsupply_mn']
   
    field_list = field_list + scarcity_field_list_ws[1:]

    # Get a dictionary from the sub-watershed shapefiles attributes based on the
    # fields to be outputted to the CSV table
    scarcity_value_dict = extract_datasource_table_by_key(
            scarcity_sheds_uri, 'ws_id', scarcity_field_list_ws)
   
    scarcity_dict_ws = combine_dictionaries(
            value_dict, scarcity_value_dict)

    LOGGER.debug('Scarcity_dict_ws : %s', scarcity_dict_ws)
    
    # Write sub-watershed CSV table
    write_new_table(scarcity_table_ws_uri, field_list, scarcity_dict_ws)
    
    valuation_checked = args.pop('valuation_container', False)
    
    if not valuation_checked:
        LOGGER.debug('Valuation Not Selected')
        # The rest of the function is valuation, so we can quit now
        return
    """
    args['valuation_table'] - a dictionary containing values of the 
        hydropower stations with the keys being watershed id and
        the values be a dictionary representing valuation information 
        corresponding to that id with the following structure (required):
        
            valuation_table[1] = {'ws_id':1, 'time_span':100, 'discount':5,
                                  'efficiency':0.75, 'fraction':0.6, 'cost':0,
                                  'height':25, 'kw_price':0.07}
        
    args['results_suffix'] - a string that will be concatenated onto the
       end of file names (optional) 
       
    returns - nothing"""
        
    # water yield functionality goes here
    LOGGER.info('Starting Valuation Calculation')
    
    # Paths for the watershed and subwatershed tables
    valuation_table_ws_uri= os.path.join(
            service_dir, 'hydropower_value_watershed.csv')
    valuation_table_sws_uri = os.path.join(
            service_dir, 'hydropower_value_subwatershed.csv') 
    
    #Open csv tables and add to the arguments
    valuation_params = {}
    valuation_table_file = open(args['valuation_table_uri'])
    reader = csv.DictReader(valuation_table_file)
    for row in reader:
        for key, val in row.iteritems():
            try:
                row[key] = float(val)
            except ValueError:
                pass

        valuation_params[int(row['ws_id'])] = row 
    
    valuation_table_file.close()
    
    valuation_sub_sheds_uri = os.path.join(output_dir, 'valuation_sub_sheds.shp')
    valuation_sheds_uri = os.path.join(output_dir, 'valuation_sheds.shp')
    raster_utils.copy_datasource_uri(sub_sheds_uri, valuation_sub_sheds_uri)
    raster_utils.copy_datasource_uri(sheds_uri, valuation_sheds_uri)
    
    energy_dict = {}
    npv_dict = {}

    compute_watershed_valuation(
            valuation_sheds_uri, scarcity_sheds_uri, valuation_params)
        
    val_field_list_ws = ['ws_id', 'hp_energy', 'hp_npv']
    
    valuation_dict_ws = extract_datasource_table_by_key(
            valuation_sheds_uri, 'ws_id', val_field_list_ws)
    
    hydropower_dict_ws = combine_dictionaries(
            scarcity_dict_ws, valuation_dict_ws)

    LOGGER.debug('Hydro WS Dict: %s', hydropower_dict_ws)

    compute_subshed_valuation(
            valuation_sub_sheds_uri, scarcity_sub_sheds_uri, hydropower_dict_ws)
    
    val_field_list_sws = ['subws_id', 'ws_id', 'hp_energy', 'hp_npv']
    
    valuation_dict_sws = extract_datasource_table_by_key(
            valuation_sub_sheds_uri, 'subws_id', val_field_list_sws)
    
    hydropower_dict_sws = combine_dictionaries(
            scarcity_dict_sws, valuation_dict_sws)
    
    sub_field_list = sub_field_list + val_field_list_sws[2:]
    field_list = field_list + val_field_list_ws[1:]
    
    write_new_table(valuation_table_sws_uri, sub_field_list, hydropower_dict_sws)
    write_new_table(valuation_table_ws_uri, field_list, hydropower_dict_ws)

def compute_subshed_valuation(val_sheds_uri, scarcity_sheds_uri, val_dict):
    """

    """
    val_ds = ogr.Open(val_sheds_uri, 1)
    val_layer = val_ds.GetLayer()
    
    scarcity_ds = ogr.Open(scarcity_sheds_uri)
    scarcity_layer = scarcity_ds.GetLayer()
    
    # The field names for the new attributes
    energy_field = 'hp_energy'
    npv_field = 'hp_npv'

    # Add the new fields to the shapefile
    for new_field in [energy_field, npv_field]:
        field_defn = ogr.FieldDefn(new_field, ogr.OFTReal)
        val_layer.CreateField(field_defn)

    num_features = val_layer.GetFeatureCount()
    # Iterate over the number of features (polygons) and compute volume
    for feat_id in xrange(num_features):
        val_feat = val_layer.GetFeature(feat_id)
        energy_id = val_feat.GetFieldIndex(energy_field)
        npv_id = val_feat.GetFieldIndex(npv_field)
        
        scarcity_feat = scarcity_layer.GetFeature(feat_id)
        ws_index = scarcity_feat.GetFieldIndex('ws_id')
        ws_id = scarcity_feat.GetField(ws_index)
        rsupply_vl_id = scarcity_feat.GetFieldIndex('rsupply_vl')
        rsupply_vl_sws = scarcity_feat.GetField(rsupply_vl_id)
        
        val_row = val_dict[ws_id]
        
        ws_rsupply_vl = val_row['rsupply_vl']
        
        npv = val_row[npv_field] * (rsupply_vl_sws / ws_rsupply_vl)
        energy = val_row[energy_field] * (rsupply_vl_sws / ws_rsupply_vl)
        
        # Get the volume field index and add value
        val_feat.SetField(energy_id, energy)
        val_feat.SetField(npv_id, npv)
        
        val_layer.SetFeature(val_feat)
    
def compute_watershed_valuation(val_sheds_uri, scarcity_sheds_uri, val_dict):
    """

    """
    val_ds = ogr.Open(val_sheds_uri, 1)
    val_layer = val_ds.GetLayer()
    
    scarcity_ds = ogr.Open(scarcity_sheds_uri)
    scarcity_layer = scarcity_ds.GetLayer()
    
    # The field names for the new attributes
    energy_field = 'hp_energy'
    npv_field = 'hp_npv'

    # Add the new fields to the shapefile
    for new_field in [energy_field, npv_field]:
        field_defn = ogr.FieldDefn(new_field, ogr.OFTReal)
        val_layer.CreateField(field_defn)

    num_features = val_layer.GetFeatureCount()
    # Iterate over the number of features (polygons) and compute volume
    for feat_id in xrange(num_features):
        val_feat = val_layer.GetFeature(feat_id)
        energy_id = val_feat.GetFieldIndex(energy_field)
        npv_id = val_feat.GetFieldIndex(npv_field)
        
        scarcity_feat = scarcity_layer.GetFeature(feat_id)
        ws_index = scarcity_feat.GetFieldIndex('ws_id')
        ws_id = scarcity_feat.GetField(ws_index)
        rsupply_vl_id = scarcity_feat.GetFieldIndex('rsupply_vl')
        rsupply_vl = scarcity_feat.GetField(rsupply_vl_id)
        
        val_row = val_dict[ws_id]
        
        # Compute hydropower energy production (KWH)
        # Not confident about units here and the constant 0.00272 is 
        # for conversion??
        energy = val_row['efficiency'] * val_row['fraction'] * val_row['height'] * rsupply_vl * 0.00272
        
        dsum = 0
        # Divide by 100 because it is input at a percent and we need
        # decimal value
        disc = val_row['discount'] / 100
        # To calculate the summation of the discount rate term over the life 
        # span of the dam we can use a geometric series
        ratio = 1 / (1 + disc)
        dsum = (1 - math.pow(ratio, val_row['time_span'])) / (1 - ratio)
        
        npv = ((val_row['kw_price'] * energy) - val_row['cost']) * dsum

        # Get the volume field index and add value
        val_feat.SetField(energy_id, energy)
        val_feat.SetField(npv_id, npv)
        
        val_layer.SetFeature(val_feat)

def combine_dictionaries(dict_1, dict_2):
    """Add dict_2 to dict_1

    """
    dict_3 = dict_1.copy()

    for key, sub_dict in dict_2.iteritems():
        for field, value in sub_dict.iteritems():
            if not field in dict_3[key].keys():
                dict_3[key][field] = value

    return dict_3

def compute_rsupply_volume(scarcity_sub_sheds_uri, wyield_sub_sheds_uri):
    """Calculate the water yield volume per sub-watershed and the water yield
        volume per hectare per sub-watershed. Add results to shape_uri, units
        are cubic meters

        shape_uri - a URI path to an ogr datasource for the sub-watershed
            shapefile. This shapefiles features should have a 'wyield_mn'
            attribute, which calculations are derived from

        returns - Nothing"""
    wyield_ds = ogr.Open(wyield_sub_sheds_uri)
    wyield_layer = wyield_ds.GetLayer()
    
    scarcity_ds = ogr.Open(scarcity_sub_sheds_uri, 1)
    scarcity_layer = scarcity_ds.GetLayer()
    
    # The field names for the new attributes
    rsupply_vol_name = 'rsupply_vl'
    rsupply_mn_name = 'rsupply_mn'

    # Add the new fields to the shapefile
    for new_field in [rsupply_vol_name, rsupply_mn_name]:
        field_defn = ogr.FieldDefn(new_field, ogr.OFTReal)
        scarcity_layer.CreateField(field_defn)

    num_features = wyield_layer.GetFeatureCount()
    # Iterate over the number of features (polygons) and compute volume
    for feat_id in xrange(num_features):
        wyield_feat = wyield_layer.GetFeature(feat_id)
        wyield_mn_id = wyield_feat.GetFieldIndex('wyield_mn')
        wyield_mn = wyield_feat.GetField(wyield_mn_id)
        
        scarcity_feat = scarcity_layer.GetFeature(feat_id)
        cyield_id = scarcity_feat.GetFieldIndex('cyield_vol')
        cyield = scarcity_feat.GetField(cyield_id)
        consump_vol_id = scarcity_feat.GetFieldIndex('consum_vol')
        consump_vol = scarcity_feat.GetField(consump_vol_id)
        consump_mn_id = scarcity_feat.GetFieldIndex('consum_mn')
        consump_mn = scarcity_feat.GetField(consump_mn_id)
       
        rsupply_vol = cyield - consump_vol
        rsupply_mn = wyield_mn - consump_mn

        # Get the volume field index and add value
        rsupply_vol_index = scarcity_feat.GetFieldIndex(rsupply_vol_name)
        scarcity_feat.SetField(rsupply_vol_index, rsupply_vol)
        rsupply_mn_index = scarcity_feat.GetFieldIndex(rsupply_mn_name)
        scarcity_feat.SetField(rsupply_mn_index, rsupply_mn)
        
        scarcity_layer.SetFeature(scarcity_feat)

def calculate_cyield_vol(
        wyield_sub_shed_uri, calib_dict, scarcity_sub_shed_uri):
    """Calculate the cyield volume for water scarcity

        wyield_sub_shed_uri - 
        calib_dict - 
        scarcity_sub_shed_uri - 

        returns nothing"""
    wyield_ds = ogr.Open(wyield_sub_shed_uri, 1)
    wyield_layer = wyield_ds.GetLayer()
    scarcity_ds = ogr.Open(scarcity_sub_shed_uri, 1)
    scarcity_layer = scarcity_ds.GetLayer()
    
    # The field names for the new attributes
    vol_name = 'wyield_vol'
    cyield_name = 'cyield_vol'

    # Add the new fields to the shapefile
    field_defn = ogr.FieldDefn(cyield_name, ogr.OFTReal)
    scarcity_layer.CreateField(field_defn)

    num_features = wyield_layer.GetFeatureCount()
    # Iterate over the number of features (polygons) and compute volume
    for feat_id in xrange(num_features):
        wyield_feat = wyield_layer.GetFeature(feat_id)
        wyield_vol_id = wyield_feat.GetFieldIndex('wyield_vol')
        wyield_vol = wyield_feat.GetField(wyield_vol_id)
        
        ws_id_index = wyield_feat.GetFieldIndex('ws_id')
        ws_id = wyield_feat.GetField(ws_id_index)
        
        # Calculate cyield 
        cyield_vol = wyield_vol * calib_dict[ws_id]

        scarcity_feat = scarcity_layer.GetFeature(feat_id)
        scarcity_cyield_id = scarcity_feat.GetFieldIndex('cyield_vol')
        scarcity_feat.SetField(scarcity_cyield_id, cyield_vol)
        
        scarcity_layer.SetFeature(scarcity_feat)

def extract_datasource_table_by_key(
        datasource_uri, key_field, wanted_list):
    """Create a dictionary lookup table of the features in the attribute table
        of the datasource referenced by datasource_uri.

        datasource_uri - a uri to an OGR datasource
        key_field - a field in datasource_uri that refers to a key (unique) value
            for each row; for example, a polygon id.
        wanted_list - a list of field names to add to the dictionary. This is
            helpful if there are fields that are not wanted to be returned

        returns a dictionary of the form {key_field_0: 
            {field_0: value0, field_1: value1}...}"""

    # Pull apart the datasource
    datasource = ogr.Open(datasource_uri)
    layer = datasource.GetLayer()
    layer_def = layer.GetLayerDefn()

    # Build up a list of field names for the datasource table
    field_names = []
    for field_id in xrange(layer_def.GetFieldCount()):
        field_def = layer_def.GetFieldDefn(field_id)
        field_names.append(field_def.GetName())

    # Loop through each feature and build up the dictionary representing the
    # attribute table
    attribute_dictionary = {}
    for feature_index in xrange(layer.GetFeatureCount()):
        feature = layer.GetFeature(feature_index)
        feature_fields = {}
        for field_name in field_names:
            if field_name in wanted_list:
                feature_fields[field_name] = feature.GetField(field_name)
        key_value = feature.GetField(key_field)
        attribute_dictionary[key_value] = feature_fields

    return attribute_dictionary
    
def write_new_table(filename, fields, data):
    """Create a new csv table from a dictionary

        filename - a URI path for the new table to be written to disk
        
        fields - a python list of the column names. The order of the fields in
            the list will be the order in how they are written. ex:
            ['id', 'precip', 'total']
        
        data - a python dictionary representing the table. The dictionary
            should be constructed with unique numerical keys that point to a
            dictionary which represents a row in the table:
            data = {0 : {'id':1, 'precip':43, 'total': 65},
                    1 : {'id':2, 'precip':65, 'total': 94}}

        returns - nothing
    """
    csv_file = open(filename, 'wb')

    #  Sort the keys so that the rows are written in order
    row_keys = data.keys()
    row_keys.sort()    

    csv_writer = csv.DictWriter(csv_file, fields)
    #  Write the columns as the first row in the table
    csv_writer.writerow(dict((fn, fn) for fn in fields))

    # Write the rows from the dictionary
    for index in row_keys:
        csv_writer.writerow(data[index])

    csv_file.close()

def compute_water_yield_volume(shape_uri):
    """Calculate the water yield volume per sub-watershed and the water yield
        volume per hectare per sub-watershed. Add results to shape_uri, units
        are cubic meters

        shape_uri - a URI path to an ogr datasource for the sub-watershed
            shapefile. This shapefiles features should have a 'wyield_mn'
            attribute, which calculations are derived from

        returns - Nothing"""
    shape = ogr.Open(shape_uri, 1)
    layer = shape.GetLayer()
    
    # The field names for the new attributes
    vol_name = 'wyield_vol'
    ha_name = 'wyield_ha'

    # Add the new fields to the shapefile
    for new_field in [vol_name, ha_name]:
        field_defn = ogr.FieldDefn(new_field, ogr.OFTReal)
        layer.CreateField(field_defn)

    num_features = layer.GetFeatureCount()
    # Iterate over the number of features (polygons) and compute volume
    for feat_id in xrange(num_features):
        feat = layer.GetFeature(feat_id)
        wyield_mn_id = feat.GetFieldIndex('wyield_mn')
        wyield_mn = feat.GetField(wyield_mn_id)
        
        geom = feat.GetGeometryRef()
        feat_area = geom.GetArea()
        
        # Calculate water yield volume
        vol = wyield_mn * feat_area / 1000.0
        # Get the volume field index and add value
        vol_index = feat.GetFieldIndex(vol_name)
        feat.SetField(vol_index, vol)

        # Calculate water yield volume per hectare
        vol_ha = vol / (0.0001 * feat_area)
        # Get the hectare field index and add value
        ha_index = feat.GetFieldIndex(ha_name)
        feat.SetField(ha_index, vol_ha)
        
        layer.SetFeature(feat)
        
def add_dict_to_shape(shape_uri, field_dict, field_name, shed_name):
    """Add a new field to a shapefile with values from a dictionary.
        The dictionaries keys should match to the values of a unique fields
        values in the shapefile

        shape_uri - a URI path to a ogr datasource on disk with a unique field
            'shed_name'. The field 'shed_name' should have values that
            correspond to the keys of 'field_dict'

        field_dict - a python dictionary with keys mapping to values. These
            values will be what is filled in for the new field 
    
        field_name - a string for the name of the new field to add
        
        shed_name - a string for the field name in 'shape_uri' that represents
            the unique features

        returns - nothing"""

    shape = ogr.Open(shape_uri, 1)
    layer = shape.GetLayer()
    
    # Create the new field
    field_defn = ogr.FieldDefn(field_name, ogr.OFTReal)
    layer.CreateField(field_defn)

    # Get the number of features (polygons) and iterate through each
    num_features = layer.GetFeatureCount()
    for feat_id in xrange(num_features):
        feat = layer.GetFeature(feat_id)
        
        # Get the index for the unique field
        ws_id = feat.GetFieldIndex(shed_name)
        
        # Get the unique value that will index into the dictionary as a key
        ws_val = feat.GetField(ws_id)
        
        # Using the unique value from the field of the feature, index into the
        # dictionary to get the corresponding value
        field_val = float(field_dict[ws_val])

        # Get the new fields index and set the new value for the field
        field_index = feat.GetFieldIndex(field_name)
        feat.SetField(field_index, field_val)

        layer.SetFeature(feat)

def sheds_map_subsheds(shape_uri, sub_shape_uri):
    """Stores which sub watersheds belong to which watershed
       
       shape - an OGR shapefile of the watersheds
       sub_shape - an OGR shapefile of the sub watersheds
       
       returns - a dictionary where the keys are the sub watersheds id's
                 and whose value is the watersheds id it belongs to
    """
    
    LOGGER.debug('Starting sheds_map_subsheds')
    shape = ogr.Open(shape_uri)
    sub_shape = ogr.Open(sub_shape_uri)
    layer = shape.GetLayer(0)
    sub_layer = sub_shape.GetLayer(0)
    collection = {}
    # For all the polygons in the watershed check to see if any of the polygons
    # in the sub watershed belong to that watershed by checking the area of the
    # watershed against the area of the Union of the watershed and sub watershed
    # polygon.  The areas will be the same if the sub watershed is part of the
    # watershed and will be different if it is not
    for feat in layer:
        index = feat.GetFieldIndex('ws_id')
        ws_id = feat.GetFieldAsInteger(index)
        geom = feat.GetGeometryRef()
        sub_layer.ResetReading()
        for sub_feat in sub_layer:
            sub_index = sub_feat.GetFieldIndex('subws_id')
            sub_id = sub_feat.GetFieldAsInteger(sub_index)
            sub_geom = sub_feat.GetGeometryRef()
            u_geom = sub_geom.Union(geom)
            # We can't be sure that the areas will be identical because of
            # floating point issues and complete accuracy so we make sure the
            # difference in areas is within reason
            # It also could be the case that the polygons were intended to 
            # overlap but do not overlap exactly
            if abs(geom.GetArea() - u_geom.GetArea()) < (math.e**-5):
                collection[sub_id] = ws_id
            
            sub_feat.Destroy()
            
        feat.Destroy()
        
    return collection

    
def write_csv_table(shed_table, field_list, file_path):
    """Creates a CSV table and writes it to disk
    
       shed_table - a dictionary where each key points to another dictionary 
                    which is a row of the csv table
       field_list - a python list of Strings that contain the ordered fields
                    for the csv file output
       file_path - a String uri that is the destination of the csv file
       
       returns - Nothing
    """
    shed_file = open(file_path, 'wb')
    writer = csv.DictWriter(shed_file, field_list)
    field_dict = {}
    # Create a dictionary with field names as keys and the same field name
    # as values, to use as first row in CSV file which will be the column header
    for field in field_list:
        field_dict[field] = field
    # Write column header row
    writer.writerow(field_dict)
    
    for sub_dict in shed_table.itervalues():
        writer.writerow(sub_dict)
    
    shed_file.close()

def sum_mean_dict(dict1, dict2, op_val):
    """Creates a dictionary by calculating the mean or sum of values over
       sub watersheds for the watershed
    
       dict1 - a dictionary whose keys are the watershed id's, which point to
               a python list whose values are the sub wateshed id's that fall
               within that watershed
       dict2 - a dictionary whose keys are sub watershed id's and
               whose values are the desired numbers to be summed or meaned
       op_val - a string indicating which operation to do ('sum' or 'mean')
       
       returns - a dictionary
    """
    new_dict = {}
    for key, val in dict1.iteritems():
        sum_ws = 0
        counter = 0
        for item in val:
            counter = counter + 1
            sum_ws = sum_ws + dict2[int(item)]
        if op_val == 'sum':
            new_dict[key] = sum_ws
        if op_val == 'mean':
            new_dict[key] = sum_ws / counter
    
    LOGGER.debug('sum_ws_dict rsupply_mean: %s', new_dict)
    return new_dict

