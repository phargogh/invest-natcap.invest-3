"""InVEST Wind Energy model """
import logging
import os
import csv
import json
import struct
import math
import tempfile
import shutil

from osgeo import gdal
from osgeo import ogr
from osgeo import osr

import numpy as np
import scipy.ndimage as ndimage
from scipy import integrate
from scipy import spatial
#required for py2exe to build
from scipy.sparse.csgraph import _validation
import shapely.wkt
import shapely.ops
from shapely import speedups

from invest_natcap import raster_utils

logging.basicConfig(format='%(asctime)s %(name)-18s %(levelname)-8s \
     %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

LOGGER = logging.getLogger('wind_energy')

speedups.enable()

class HubHeightError(Exception):
    """A custom error message for a hub height that is not supported in
        the current wind data
    """
    pass

def execute(args):
    """This module handles the execution of the wind energy model
        given the following dictionary:
    
        args[workspace_dir] - a python string which is the uri path to where the
            outputs will be saved (required)
        args[wind_data_uri] - a text file where each row is a location with at
            least the Longitude, Latitude, Scale and Shape parameters (required)
        args[aoi_uri] - a uri to an OGR datasource that is of type polygon and 
            projected in linear units of meters. The polygon specifies the 
            area of interest for the wind data points. If limiting the wind 
            farm bins by distance, then the aoi should also cover a portion 
            of the land polygon that is of interest (optional for biophysical
            and no distance masking, required for biophysical and distance
            masking, required for valuation)
        args[bathymetry_uri] - a uri to a GDAL dataset that has the depth
            values of the area of interest (required)
        args[global_wind_parameters_uri] - a uri to a CSV file that holds the
            global parameter values for both the biophysical and valuation
            module (required)        
        args[bottom_type_uri] - a uri to an OGR datasource of type polygon
            that depicts the subsurface geology type (optional)
        args[turbine_parameters_uri] - a uri to a CSV file that holds the
            turbines biophysical parameters as well as valuation parameters 
            (required)
        args[number_of_machines] - an integer value for the number of machines
            for the wind farm (required for valuation)
        args[min_depth] - a float value for the minimum depth for offshore wind
            farm installation (meters) (required)
        args[max_depth] - a float value for the maximum depth for offshore wind
            farm installation (meters) (required)
        args[suffix] - a String to append to the end of the output files
            (optional)
        args[land_polygon_uri] - a uri to an OGR datasource of type polygon that
            provides a coastline for determining distances from wind farm bins.
            Enabled by AOI and required if wanting to mask by distances or
            run valuation
        args[min_distance] - a float value for the minimum distance from shore
            for offshore wind farm installation (meters) The land polygon must
            be selected for this input to be active (optional, required for 
            valuation)
        args[max_distance] - a float value for the maximum distance from shore
            for offshore wind farm installation (meters) The land polygon must
            be selected for this input to be active (optional, required for 
            valuation)
        args[grid_points_uri] - a uri to a CSV file that specifies the landing
            and grid point locations (optional)
        args[foundation_cost] - a float representing how much the foundation
            will cost for the specific type of turbine (required for valuation)
        args[dollar_per_kWh] - a float value for the amount of dollars per
            kilowatt hour (kWh) (required for valuation)
        args[discount_rate] - a float value for the discount rate (required for
            valuation)
        args[avg_grid_distance] - a float for the average distance in kilometers
            from a grid connection point to a land connection point 
            (required for valuation if grid connection points are not provided)

        returns - nothing"""
    
    LOGGER.debug('Starting the Wind Energy Model')

    workspace = args['workspace_dir']
    intermediate_dir = os.path.join(workspace, 'intermediate') 
    output_dir = os.path.join(workspace, 'output') 
    raster_utils.create_directories([workspace, intermediate_dir, output_dir])
            
    # Append a _ to the suffix if it's not empty and doens't already have one
    try:
        file_suffix = args['suffix']
        if file_suffix != "" and not file_suffix.startswith('_'):
            file_suffix = '_' + file_suffix
    except KeyError:
        file_suffix = ''

    # Create a list of the biophysical parameters we are looking for from the
    # input files
    biophysical_params = ['cut_in_wspd', 'cut_out_wspd', 'rated_wspd',
                          'hub_height', 'turbine_rated_pwr', 'air_density',
                          'exponent_power_curve', 'air_density_coefficient',
                          'loss_parameter', 'turbines_per_circuit', 
                          'rotor_diameter', 'rotor_diameter_factor']

    # Get the biophysical turbine parameters from the CSV file
    bio_turbine_param_file = open(args['turbine_parameters_uri'])
    bio_turbine_reader = csv.reader(bio_turbine_param_file)
    bio_turbine_dict = {}
    for field_value_row in bio_turbine_reader:
        # Only get the biophysical parameters and leave out the valuation ones
        if field_value_row[0].lower() in biophysical_params:
            bio_turbine_dict[field_value_row[0].lower()] = field_value_row[1]

    # Get the global parameters for biophysical from the CSV file
    global_bio_param_file = open(args['global_wind_parameters_uri'])
    global_bio_reader = csv.reader(global_bio_param_file)
    for field_value_row in global_bio_reader:
        # Only get the biophysical parameters and leave out the valuation ones
        if field_value_row[0].lower() in biophysical_params:
            bio_turbine_dict[field_value_row[0].lower()] = field_value_row[1]

    LOGGER.debug('Biophysical Turbine Parameters: %s', bio_turbine_dict)
    
    # Check that all the necessary input fields from the CSV files have been
    # collected by comparing the number of dictionary keys to the number of
    # elements in our known list
    if len(bio_turbine_dict.keys()) != len(biophysical_params):
        class FieldError(Exception):
            """A custom error message for fields that are missing"""
            pass
        raise FieldError('An Error occured from reading in a field value from '
        'either the turbine CSV file or the global parameters JSON file. ' 
        'Please make sure all the necessary fields are present and spelled '
        'correctly.')
    
    # Using the hub height to generate the proper field name for the scale 
    # value that is found in the wind data file
    hub_height = int(bio_turbine_dict['hub_height'])

    if hub_height % 10 != 0:
        raise HubHeightError('An Error occurred processing the Hub Height. '
                'Please make sure the Hub Height is between the ranges of 10 '
                'and 150 meters and is a multiple of 10. ex: 10,20,...70,80...')

    scale_key = str(hub_height)
    if len(scale_key) <= 2:
        scale_key = 'Ram-0' + scale_key + 'm'
    else:
        scale_key = 'Ram-' + scale_key + 'm'
   
    # Define a list of the fields that are of interest in the wind data file
    wind_data_field_list = ['LATI', 'LONG', scale_key, 'K-010m']

    # Read the wind energy data into a dictionary
    LOGGER.info('Read wind data from text file')
    wind_data = read_binary_wind_data(args['wind_data_uri'], wind_data_field_list)
   
    aoi_uri = None
    if 'aoi_uri' in args:
        aoi_uri = args['aoi_uri']
        LOGGER.info('AOI Provided')
        # Since an AOI was provided the wind energy points shapefile will need
        # to be clipped and projected. Thus save the construction of the
        # shapefile from dictionary in the intermediate directory
        wind_point_shape_uri = os.path.join(
                inter_dir, 'wind_energy_points_from_data' + suffix + '.shp')
        
        LOGGER.info('Create point shapefile from wind data')
        
        wind_data_to_point_shape(wind_data, 'wind_data', wind_point_shape_uri)
        
        # Define the uri for projecting the wind energy data points
        wind_points_proj_uri = os.path.join(
                out_dir, 'wind_energy_points' + suffix + '.shp')

        # Clip and project the wind energy points datasource
        LOGGER.debug('Clip and project wind points to AOI')
        clip_and_reproject_shapefile(
                wind_data_points, aoi_uri, wind_points_proj_uri) 
    
        # Define the uri for projecting the bathymetry
        bathymetry_proj_uri = os.path.join(
                inter_dir, 'bathymetry_projected' + suffix + '.tif')
        
        # Clip and project the bathymetry dataset
        LOGGER.debug('Clip and project bathymetry to AOI')
        #clip_and_proj_bath =
        clip_and_reproject_raster(bathymetry_uri, aoi_uri, bathymetry_proj_uri)

        bathymetry_uri = bathymetry_proj_uri
        wind_data_points_uri = wind_points_proj_uri
        
        # Try to handle the distance inputs and land datasource if they 
        # are present
        try:
            min_distance = float(args['min_distance'])
            max_distance = float(args['max_distance'])
            land_polygon_uri = args['land_polygon_uri']
        except KeyError:
            LOGGER.info('Distance information not provided')
            dist_data_provided = False 
        else: 
            LOGGER.info('Handling distance parameters')
            dist_data_provided = True

            # Define the uri for reprojecting the land polygon datasource
            land_poly_proj_uri = os.path.join(
                    inter_dir, 'land_poly_projected' + suffix + '.shp')
            # Clip and project the land polygon datasource 
            LOGGER.debug('Clip and project land poly to AOI')
            clip_and_reproject_shapefile(
                    land_polygon_uri, aoi_uri, land_poly_proj_uri)

            land_polygon_uri = land_poly_proj_uri
    else:
        LOGGER.info("AOI argument was not selected")
        
        # Since no AOI was provided the wind energy points shapefile that is
        # created directly from dictionary will be the final output, so set the
        # uri to point to the output folder
        wind_point_shape_uri = os.path.join(
                out_dir, 'wind_energy_points' + suffix + '.shp')
        
        LOGGER.debug('Create point shapefile from wind data')
        
        wind_data_to_point_shape(wind_data, 'wind_data', wind_point_shape_uri)
        
        wind_data_points_uri = wind_point_shape_uri
        bathymetry_uri = args['bathymetry_uri']
    
    # Get the min and max depth values from the arguments and set to a negative
    # value indicating below sea level
    min_depth = abs(float(args['min_depth'])) * -1.0
    max_depth = abs(float(args['max_depth'])) * -1.0
    # Get the number of turbines from the arguments
    number_of_turbines = int(args['number_of_machines'])

    #STARTTING BIOPHYSICAL CORE 
    out_nodata = raster_utils.get_nodata_from_uri(bathymetry_uri)
    
    def depth_op(bath):
        """A vectorized function that takes one argument and uses a range to
            determine if that value falls within the range
            
            bath - an integer value of either positive or negative
            min_depth - a float value specifying the lower limit of the range.
                this value is set above
            max_depth - a float value specifying the upper limit of the range
                this value is set above
            out_nodata - a int or float for the nodata value described above

            returns - out_nodata if 'bath' does not fall within the range, or
                'bath' if it does"""
        if bath >= max_depth and bath <= min_depth:
            return bath
        else:
            return out_nodata

    depth_mask_uri = os.path.join(intermediate_dir, 'depth_mask' + tif_suffix)
    
    LOGGER.info('Creating Depth Mask')
    # Create a mask for any values that are out of the range of the depth values
    cell_size = raster_utils.get_cell_size_from_uri(bathymetry_uri)
    
    raster_utils.vectorize_datasets(
            [bathymetry_uri], depth_op, depth_mask_uri, gdal.GDT_Float32,
            out_nodata, cell_size, 'intersection')

    # Handle the AOI if it was passed in with the dictionary
    if aoi_uri != None:    
        LOGGER.info('AOI provided')

        # If the distance inputs are present create a mask for the output
        # area that restricts where the wind energy farms can be based
        # on distance
        if dist_data_provided:
            aoi_raster_uri = os.path.join(
                    intermediate_dir, 'aoi_raster' + tif_suffix)

            LOGGER.info('Create Raster From AOI')
            # Make a raster from the AOI using the bathymetry rasters pixel size 
            raster_utils.create_raster_from_vector_extents_uri(
                aoi_uri, cell_size, gdal.GDT_Float32, out_nodata,
                aoi_raster_uri) 
            
            LOGGER.info('Rasterize AOI onto raster')
            # Burn the area of interest onto the raster 
            rasterize_layer_uri(
                aoi_raster_uri, aoi_uri, 1, field=None,
                option_list="ALL_TOUCHED=TRUE")

            LOGGER.info('Rasterize Land Polygon onto raster')
            # Burn the land polygon onto the raster, covering up the AOI values
            # where they overlap
            rasterize_layer_uri(
                aoi_raster_uri, land_polygon_uri, 0, field=None,
                option_list="ALL_TOUCHED=TRUE")

            dist_mask_uri = os.path.join(
                    intermediate_dir, 'distance_mask' + tif_suffix)
            
            LOGGER.info('Generate Distance Mask')
            # Create a distance mask
            distance_transform_dataset(
                    aoi_raster_uri, min_distance, max_distance, 
                    out_nodata, dist_mask_uri)
        else:
            # Looks like distances weren't provided, too bad!
            LOGGER.info('Distance parameters not provided')
    else:
        LOGGER.info('AOI not provided')

    LOGGER.debug('hub_height : %s', hub_height)
    LOGGER.debug('SCALE_key : %s', scale_key)

    # The String name for the shape field. So far this is a default from the
    # text file given by CK. I guess we could search for the 'K' if needed.
    shape_key = 'K-010m'

    # Weibull probability function to integrate over
    def weibull_probability(v_speed, k_shape, l_scale):
        """Calculate the weibull probability function of variable v_speed
            
            v_speed - a number representing wind speed
            k_shape - a float for the shape parameter
            l_scale - a float for the scale parameter of the distribution
  
            returns - a float"""
        return ((k_shape / l_scale) * (v_speed / l_scale)**(k_shape - 1) *
                (math.exp(-1 * (v_speed/l_scale)**k_shape)))

    # Density wind energy function to integrate over
    def density_wind_energy_fun(v_speed, k_shape, l_scale):
        """Calculate the probability density function of a weibull variable
            v_speed
            
            v_speed - a number representing wind speed
            k_shape - a float for the shape parameter
            l_scale - a float for the scale parameter of the distribution
  
            returns - a float"""
        return ((k_shape / l_scale) * (v_speed / l_scale)**(k_shape - 1) *
                (math.exp(-1 * (v_speed/l_scale)**k_shape))) * v_speed**3
    
    # Harvested wind energy function to integrate over
    def harvested_wind_energy_fun(v_speed, k_shape, l_scale):
        """Calculate the harvested wind energy

            v_speed - a number representing wind speed
            k_shape - a float for the shape parameter
            l_scale - a float for the scale parameter of the distribution

            returns - a float"""
        fract = ((v_speed**exp_pwr_curve - v_in**exp_pwr_curve) /
            (v_rate**exp_pwr_curve - v_in**exp_pwr_curve))
   
        return fract * weibull_probability(v_speed, k_shape, l_scale) 

    # Get the inputs needed to compute harvested wind energy
    exp_pwr_curve = int(bio_turbine_dict['exponent_power_curve'])
    
    # The harvested energy is on a per year basis
    num_days = 365 
    
    # The rated power is expressed in units of MW but the harvested energy
    # equation calls for it in terms of Wh. Thus we multiply by a million to get
    # to Wh.
    rated_power = float(bio_turbine_dict['turbine_rated_pwr']) * 1000000

    air_density_standard = float(bio_turbine_dict['air_density'])
    v_rate = float(bio_turbine_dict['rated_wspd'])
    v_out = float(bio_turbine_dict['cut_out_wspd'])
    v_in = float(bio_turbine_dict['cut_in_wspd'])
    air_density_coef = float(bio_turbine_dict['air_density_coefficient'])
    losses = float(bio_turbine_dict['loss_parameter'])
    number_of_turbines = args['number_of_turbines']

    # Compute the mean air density, given by CKs formulas
    mean_air_density = air_density_standard - air_density_coef * hub_height

    # Fractional coefficient that lives outside the intregation for computing
    # the harvested wind energy
    fract_coef = rated_power * (mean_air_density / air_density_standard)
    
    # The coefficient that is multiplied by the integration portion of the
    # harvested wind energy equation
    scalar = num_days * 24 * fract_coef
    density_field_name = 'Dens_W/m2'
    harvest_field_name = 'Harv_MWhr'

    def compute_density_harvested_uri(wind_pts_uri):
        wind_points = ogr.Open(wind_pts_uri, 1)
        wind_points_layer = wind_points.GetLayer()
        feature = wind_points_layer.GetFeature(0)
        
        # Get the indexes for the scale and shape parameters
        scale_index = feature.GetFieldIndex(scale_key)
        shape_index = feature.GetFieldIndex(shape_key)
        LOGGER.debug('scale/shape index : %s:%s', scale_index, shape_index)
        wind_points_layer.ResetReading()

        LOGGER.info('Creating Harvest and Density Fields')
        # Create new fields for the density and harvested values
        for new_field_name in [density_field_name, harvest_field_name]:
            new_field = ogr.FieldDefn(new_field_name, ogr.OFTReal)
            wind_points_layer.CreateField(new_field)

        LOGGER.info('Entering Density and Harvest Calculations for each point')
        # For all the locations compute the weibull density and 
        # harvested wind energy. Save in a field of the feature
        for feat in wind_points_layer:
            # Get the scale and shape values
            scale_value = feat.GetField(scale_index)
            shape_value = feat.GetField(shape_index)
            
            # Integrate over the probability density function. 0 and 50 are hard
            # coded values set in CKs documentation
            density_results = integrate.quad(
                    density_wind_energy_fun, 0, 50, (shape_value, scale_value))

            # Compute the final wind power density value
            density_results = 0.5 * mean_air_density * density_results[0]

            # Integrate over the harvested wind energy function
            harv_results = integrate.quad(
                    harvested_wind_energy_fun, v_in, v_rate, 
                    (shape_value, scale_value))
            
            # Integrate over the weibull probability function
            weibull_results = integrate.quad(weibull_probability, v_rate, v_out,
                    (shape_value, scale_value))
            
            # Compute the final harvested wind energy value
            harvested_wind_energy = scalar * (harv_results[0] + weibull_results[0])
           
            # Convert harvested energy from Whr/yr to MWhr/yr by dividing by
            # 1,000,000
            harvested_wind_energy = harvested_wind_energy / 1000000.00

            # Now factor in the percent losses due to turbine
            # downtime (mechanical failure, storm damage, etc.)
            # and due to electrical resistance in the cables 
            harvested_wind_energy = (1 - losses) * harvested_wind_energy

            # Finally, multiply the harvested wind energy by the number of turbines
            # to get the amount of energy generated for the entire farm
            harvested_wind_energy = harvested_wind_energy * number_of_turbines

            # Save the results to their respective fields 
            for field_name, result_value in [(density_field_name, density_results),
                    (harvest_field_name, harvested_wind_energy)]:
                out_index = feat.GetFieldIndex(field_name)
                feat.SetField(out_index, result_value)

            # Save the feature and set to None to clean up
            wind_points_layer.SetFeature(feat)
            feat = None

        wind_points = None
    
    compute_density_harvested_uri(wind_data_points_uri)

    # Create rasters for density and harvested values
    density_temp_uri = raster_utils.temporary_filename() 
    harvested_temp_uri = raster_utils.temporary_filename() 
    
    LOGGER.info('Create Density Raster')
    raster_utils.create_raster_from_vector_extents_uri(
            wind_points_uri, cell_size, gdal.GDT_Float32, out_nodata,
            density_temp_uri)
    
    LOGGER.info('Create Harvested Raster')
    raster_utils.create_raster_from_vector_extents_uri(
            wind_points_uri, cell_size, gdal.GDT_Float32, out_nodata,
            harvested_temp_uri)

    # Interpolate points onto raster for density values and harvested values:
    LOGGER.info('Vectorize Density Points')
    raster_utils.vectorize_points_uri(
            wind_points_uri, density_field_name, density_temp_uri,
            interpolation = 'linear')
    
    LOGGER.info('Vectorize Harvested Points')
    raster_utils.vectorize_points_uri(
            wind_points_uri, harvest_field_name, harvested_temp_uri,
            interpolation = 'linear')

    def mask_out_depth_dist(*rasters):
        """Returns the value of the first item in the list if and only if all 
            other values are not a nodata value. 
            
            *rasters - a list of values as follows:
                rasters[0] - the desired output value (required)
                rasters[1] - the depth mask value (required)
                rasters[2] - the distance mask value (optional)

            returns - a float of either out_nodata or rasters[0]"""
        
        if out_nodata in rasters:
            return out_nodata
        else:
            return rasters[0] 

    density_masked_uri = os.path.join(output_dir, 'density_W_per_m2' + tif_suffix)
    harvested_masked_uri = os.path.join(
            output_dir, 'harvested_energy_MWhr_per_yr' + tif_suffix)

    density_mask_list = [density_temp, depth_mask]
    harvest_mask_list = [harvested_temp, depth_mask]

    # If a distance mask was created then add it to the raster list to pass in
    # for masking out the output datasets
    try:
        density_mask_list.append(distance_mask)
        harvest_mask_list.append(distance_mask)
    except NameError:
        LOGGER.info('NO Distance Mask')

    # Mask out any areas where distance or depth has determined that wind farms
    # cannot be located
    LOGGER.info('Vectorize Rasters on Density using depth and distance mask')
    raster_utils.vectorize_datasets(
            [density_mask_uri], mask_out_depth_dist, density_masked_uri,
            gdal.GDT_Float32, out_nodata, cell_size, 'intersection')

    LOGGER.info('Vectorize Rasters on Harvested using depth and distance mask')
    raster_utils.vectorize_datasets(
            [harvest_mask_uri], mask_out_depth_dist, harvested_masked_uri,
            gdal.GDT_Float32, out_nodata, cell_size, 'intersection')

    # Create the farm polygon shapefile, which is an example of how big the farm
    # will be with a rough representation of its dimensions. 
    LOGGER.info('Creating Farm Polygon')
    # The number of turbines allowed per circuit for infield cabling
    turbines_per_circuit = int(bio_turbine_dict['turbines_per_circuit'])
    # The rotor diameter of the turbines
    rotor_diameter = int(bio_turbine_dict['rotor_diameter'])
    # The rotor diameter factor is a rule by which to use in deciding how far
    # apart the turbines should be spaced
    rotor_diameter_factor = int(bio_turbine_dict['rotor_diameter_factor'])

    # Calculate the number of circuits there will be based on the number of
    # turbines and the number of turbines per circuit. If a fractional value is
    # returned we want to round up and error on the side of having the farm be
    # slightly larger
    num_circuits = math.ceil(float(number_of_turbines) / turbines_per_circuit)
    # The distance needed between turbines
    spacing_dist = rotor_diameter * rotor_diameter_factor

    # Calculate the width
    width = (num_circuits - 1) * spacing_dist
    # Calculate the length 
    length = (turbines_per_circuit - 1) * spacing_dist
    
    pt_geometry = get_highest_harvested_geom(wind_points_uri)
    # Get the X and Y location for the selected wind farm point. These
    # coordinates will be the starting point of which to create the farm lines
    center_x = pt_geometry.GetX()
    center_y = pt_geometry.GetY()
    start_point = (center_x, center_y)
    #spat_ref = wind_points_layer.GetSpatialRef()
    spat_ref = raster_utils.get_spatial_ref_uri(wind_points_uri)
    
    farm_poly_uri = os.path.join(output_dir,
            'example_size_and_orientation_of_a_possible_wind_farm' + shp_suffix)
    
    if os.path.isfile(farm_poly_uri):
        os.remove(farm_poly_uri)

    create_wind_farm_box(spat_ref, start_point, width, length, farm_poly_uri)
    
    LOGGER.info('Leaving Wind Energy Biophysical Core')

def create_wind_farm_box(spat_ref, start_point, x_len, y_len, out_uri): 
    """Create an OGR shapefile where the geometry is a set of lines 

        spat_ref - a SpatialReference to use in creating the output shapefile
            (required)
        start_point - a tuple of floats indicating the first vertice of the 
            line (required)
        x_len - an integer value for the length of the line segment in
            the X direction (required)
        y_len - an integer value for the length of the line segment in
            the Y direction (required)
        out_uri - a string representing the file path to disk for the new
            shapefile (required)
    
        return - an OGR shapefile"""
    LOGGER.info('Entering create_wind_farm_box')

    driver = ogr.GetDriverByName('ESRI Shapefile')
    datasource = driver.CreateDataSource(out_uri)
  
    # Create the layer name from the uri paths basename without the extension
    uri_basename = os.path.basename(out_uri)
    layer_name = os.path.splitext(uri_basename)[0]
    
    layer = datasource.CreateLayer(layer_name, spat_ref, ogr.wkbLineString)

    # Add a single ID field
    field = ogr.FieldDefn('id', ogr.OFTReal)
    layer.CreateField(field)

    # Create the 3 other points that will make up the vertices for the lines 
    top_left = (start_point[0], start_point[1] + y_len)
    top_right = (start_point[0] + x_len, start_point[1] + y_len)
    bottom_right = (start_point[0] + x_len, start_point[1])

    # Create a new feature, setting the field and geometry
    line = ogr.Geometry(ogr.wkbLineString)
    line.AddPoint(start_point[0], start_point[1])
    line.AddPoint(top_left[0], top_left[1])
    line.AddPoint(top_right[0], top_right[1])
    line.AddPoint(bottom_right[0], bottom_right[1])
    line.AddPoint(start_point[0], start_point[1])
    
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetGeometry(line)
    feature.SetField(0, 1)
    layer.CreateFeature(feature)

    feature = None
    layer = None

    datasource.SyncToDisk()
    datasource = None
    LOGGER.info('Leaving create_wind_farm_box')

def get_highest_harvested_geom(wind_points_uri):
    """Find the point with the highest harvested value for wind energy and
        return its geometry

        wind_points_uri - a URI to an OGR Datasource of a point geometry
            shapefile for wind energy

        returns - the geometry of the point with the highest harvested value
        """

        wind_points = ogr.Open(wind_points_uri)
        layer = wind_points.GetLayer()
    
        geom = None
        harv_value = None
        high_harv_value = 0.0

        feature = layer.GetNextFeature()
        harv_index = feature.GetFieldIndex('Harv_MWhr')
        high_harv_value = feature.GetField(harv_index)
        geom = feature.GetGeometryRef()

        for feat in layer:
            harv_value = feat.GetField(harv_index)
            if harv_value > high_harv_value:
                high_harv_value = harv_value
                geom = feat.GetGeometryRef()
        
        wind_points = None
        return geom

def distance_transform_dataset(
        dataset_uri, min_dist, max_dist, out_nodata, out_uri):
    """A memory efficient distance transform function that operates on 
       the dataset level and creates a new dataset that's transformed.
       It will treat any nodata value in dataset as 0, and re-nodata
       that area after the filter.

       dataset - a gdal dataset
       min_dist - an integer of the minimum distance allowed in meters
       max_dist - an integer of the maximum distance allowed in meters
       out_uri - the uri output of the transformed dataset
       out_nodata - the nodata value of dataset

       returns the transformed dataset created at out_uri"""
    
    dataset = gdal.Open(dataset_uri)
    # Define URI paths for the numpy arrays on disk
    temp_dir = tempfile.mkdtemp()
    source_filename = os.path.join(temp_dir, 'source.dat')
    nodata_mask_filename = os.path.join(temp_dir, 'nodata_mask.dat')
    dest_filename = os.path.join(temp_dir, 'dest.dat')

    mask_leq_min_dist_filename = os.path.join(temp_dir, 'mask_leq_min_dist.dat')
    mask_geq_max_dist_filename = os.path.join(temp_dir, 'mask_geq_max_dist.dat')
    dest_mask_filename = os.path.join(temp_dir, 'dest_mask.dat')

    source_band, source_nodata = raster_utils.extract_band_and_nodata(dataset)
    pixel_size = raster_utils.pixel_size(dataset)
    LOGGER.debug('Pixel Size : %s', pixel_size)

    out_dataset = raster_utils.new_raster_from_base(
        dataset, out_uri, 'GTiff', out_nodata, gdal.GDT_Float32)
    out_band, out_nodata = raster_utils.extract_band_and_nodata(out_dataset)

    shape = (source_band.YSize, source_band.XSize)
    LOGGER.debug('shape %s' % str(shape))

    LOGGER.debug('make the source memmap at %s' % source_filename)
    # Create the numpy memory maps
    source_array = np.memmap(
        source_filename, dtype='float32', mode='w+', shape = shape)
    nodata_mask_array = np.memmap(
        nodata_mask_filename, dtype='bool', mode='w+', shape = shape)
    dest_array = np.memmap(
        dest_filename, dtype='float32', mode='w+', shape = shape)
    mask_leq_min_dist_array = np.memmap(
        mask_leq_min_dist_filename, dtype='bool', mode='w+', shape = shape)
    mask_geq_max_dist_array = np.memmap(
        mask_geq_max_dist_filename, dtype='bool', mode='w+', shape = shape)
    dest_mask_array = np.memmap(
        dest_mask_filename, dtype='bool', mode='w+', shape = shape)

    LOGGER.debug('load dataset into source array')
    # Load the dataset into the first memory map
    for row_index in xrange(source_band.YSize):
        #Load a row so we can mask
        row_array = source_band.ReadAsArray(0, row_index, source_band.XSize, 1)
        #Just the mask for this row
        mask_row = row_array == source_nodata
        row_array[mask_row] = 1.0
        source_array[row_index, :] = row_array

        #remember the mask in the memory mapped array
        nodata_mask_array[row_index, :] = mask_row
    
    LOGGER.info('distance transform operation')
    # Calculate distances using distance transform and multiply by the pixel
    # size to get the proper distances in meters
    dest_array = ndimage.distance_transform_edt(source_array) * pixel_size
    
    # Use conditional operations to properly get masks based on distance values
    np.less_equal(dest_array, min_dist, out = mask_leq_min_dist_array)
    np.greater_equal(dest_array, max_dist, out = mask_geq_max_dist_array)
    
    # Take the logical OR of the above masks to get the proper values that fall
    # between the min and max distances
    np.logical_or(
            mask_leq_min_dist_array, mask_geq_max_dist_array,
            out = dest_mask_array)
    
    dest_array[dest_mask_array] = out_nodata

    LOGGER.debug('mask the result back to nodata where originally nodata')
    dest_array[nodata_mask_array] = out_nodata
    
    LOGGER.debug('write to gdal object')
    out_band.WriteArray(dest_array)
    out_dataset.FlushCache()
    raster_utils.calculate_raster_stats(out_dataset)

    LOGGER.debug('deleting %s' % temp_dir)
    dest_array = None
    nodata_mask_array = None
    source_array = None
    out_band = None
    mask_leq_min_dist_array = None
    mask_geq_max_dist_array = None
    dest_mask_array = None
    
    #Turning on ignore_errors = True in case we can't remove the 
    #the temporary directory
    shutil.rmtree(temp_dir, ignore_errors = True)

    out_dataset.FlushCache()
    return out_dataset

def rasterize_layer_uri(
        raster_uri, shapefile_uri, burn_value, field=None, option_list=None):
    """Burn the layer from 'shapefile_uri' onto the raster from 'raster_uri'.
        Will burn 'burn_value' onto the raster unless 'field' is not None,
        in which case it will burn the value from shapefiles field.

        raster_uri - a URI to a gdal dataset
        shapefile_uri - a URI to an ogr datasource
        burn_value - a Python number to burn into the raster
        field - the name of a field from 'shapefile_uri' to use as the burn
            value (optional)
        option_list - a Python list of options for the operation. Example:
            ["ATTRIBUTE=NPV", "ALL_TOUCHED=TRUE"]

        returns - Nothing

        
    """

    raster = gdal.Open(raster_uri, 1)
    shapefile = ogr.Open(shapefile_uri)
    layer = shapefile.GetLayer()

    if field != None:
        gdal.RasterizeLayer(raster, [1], layer, options = option_list)
    else:
        gdal.RasterizeLayer(
                raster, [1], layer, burn_values = [burn_value], options = option_list)

    raster = None
    shapefile = None

def read_binary_wind_data(wind_data_uri, field_list):
    """Unpack the binary wind data into a dictionary. This function only reads
        binary files that are packed using big indian ordering '<'. Each piece
        of data is 4 bytes long and of type float. Each row of the file has data
        that corresponds to the following fields:

            "LONG","LATI","Ram-010m","Ram-020m","Ram-030m","Ram-040m",
            "Ram-050m","Ram-060m","Ram-070m","Ram-080m","Ram-090m","Ram-100m",
            "Ram-110m","Ram-120m","Ram-130m","Ram-140m","Ram-150m","K-010m"
        
        wind_data_uri - a uri for the binary wind data file
        field_list - a list of strings referring to the column headers from
            the text file that are to be included in the dictionary.
            ['LONG', 'LATI', scale_key, 'K-010m']

        returns - a dictionary where the keys are lat/long tuples which point
            to dictionaries that hold wind data at that location"""

    LOGGER.debug('Entering read_wind_data')
   
    wind_dict = {}

    # This is the expected column header list for the binary wind energy file.
    # It is expected that the data will be in this order so that we can properly
    # unpack the information into a dictionary
    param_list = [
            "LONG","LATI","Ram-010m","Ram-020m","Ram-030m","Ram-040m",
            "Ram-050m","Ram-060m","Ram-070m","Ram-080m","Ram-090m","Ram-100m",
            "Ram-110m","Ram-120m","Ram-130m","Ram-140m","Ram-150m","K-010m"]
   
    # Get the scale key from the field list to verify that the hub height given
    # is indeed a valid height handled in the wind energy point data
    scale_key = field_list[2]
    
    if scale_key not in param_list:
        raise HubHeightError('The Hub Height is not supported by the current '
                'wind point data. Please make sure the hub height lies '
                'between 10 and 150 meters')

    # Open the file in reading and binary mode
    wind_file = open(wind_data_uri, 'rb')
    
    # Get the length of the expected parameter list to use in unpacking
    param_list_length = len(param_list)

    # For every line in the file, unpack
    while True:
        # Read in line by line where each piece of data is 4 bytes
        line = wind_file.read(4*param_list_length)
        
        # If we have reached the end of the file, quit
        if len(line) == 0:
            break
        
        # Unpack the data. We are assuming the binary data was packed using the
        # big indian ordering '<' and that the values are floats.
        values_list = struct.unpack('<'+'f'*param_list_length, line)

        # The key of the output dictionary will be a tuple of the latitude,
        # longitude
        key = (values_list[1], values_list[0])
        wind_dict[key] = {}

        for index in range(param_list_length):
            # Only add the field and values we are interested in using
            if param_list[index] in field_list:
                # Build up the dictionary with values
                wind_dict[key][param_list[index]] = values_list[index]

    wind_file.close()

    LOGGER.debug('Leaving read_wind_data')
    return wind_dict

def wind_data_to_point_shape(dict_data, layer_name, output_uri):
    """Given a dictionary of the wind data create a point shapefile that
        represents this data
        
        dict_data - a python dictionary with the wind data, where the keys are
            tuples of the lat/long coordinates:
            {
            (97, 43) : {'LATI':97, 'LONG':43, 'Ram-030m':6.3, 'K-010m':2.7},
            (55, 51) : {'LATI':55, 'LONG':51, 'Ram-030m':6.2, 'K-010m':2.4},
            (73, 47) : {'LATI':73, 'LONG':47, 'Ram-030m':6.5, 'K-010m':2.3}
            }
        layer_name - a python string for the name of the layer
        output_uri - a uri for the output destination of the shapefile

        return - nothing"""
    
    LOGGER.debug('Entering wind_data_to_point_shape')
    
    # If the output_uri exists delete it
    if os.path.isfile(output_uri):
        os.remove(output_uri)
   
    LOGGER.debug('Creating new datasource')
    output_driver = ogr.GetDriverByName('ESRI Shapefile')
    output_datasource = output_driver.CreateDataSource(output_uri)

    # Set the spatial reference to WGS84 (lat/long)
    source_sr = osr.SpatialReference()
    source_sr.SetWellKnownGeogCS("WGS84")
    
    output_layer = output_datasource.CreateLayer(
            layer_name, source_sr, ogr.wkbPoint)

    # Construct a list of fields to add from the keys of the inner dictionary
    field_list = dict_data[dict_data.keys()[0]].keys()
    LOGGER.debug('field_list : %s', field_list)

    LOGGER.debug('Creating fields for the datasource')
    for field in field_list:
        output_field = ogr.FieldDefn(field, ogr.OFTReal)   
        output_layer.CreateField(output_field)

    LOGGER.debug('Entering iteration to create and set the features')
    # For each inner dictionary (for each point) create a point
    for point_dict in dict_data.itervalues():
        latitude = float(point_dict['LATI'])
        longitude = float(point_dict['LONG'])

        geom = ogr.Geometry(ogr.wkbPoint)
        geom.AddPoint_2D(longitude, latitude)

        output_feature = ogr.Feature(output_layer.GetLayerDefn())
        output_layer.CreateFeature(output_feature)
        
        for field_name in point_dict:
            field_index = output_feature.GetFieldIndex(field_name)
            output_feature.SetField(field_index, point_dict[field_name])
        
        output_feature.SetGeometryDirectly(geom)
        output_layer.SetFeature(output_feature)
        output_feature = None

    LOGGER.debug('Leaving wind_data_to_point_shape')
    output_datasource = None

def clip_and_reproject_raster(
        raster_uri, aoi_uri, projected_uri):
    """Clip and project a Dataset to an area of interest

        raster_uri - a URI to a gdal Dataset
        aoi_uri - a URI to a ogr DataSource of geometry type polygon
        projected_uri - a URI string for the output dataset to be written to
            disk

        returns - a Dataset clipped and projected to an area of interest"""

    LOGGER.debug('Entering clip_and_reproject_raster')
    # Get the AOIs spatial reference as strings in Well Known Text
    aoi_sr = raster_utils.get_spatial_ref_uri(aoi_uri)
    aoi_wkt = aoi_sr.ExportToWkt()

    # Get the Well Known Text of the raster
    raster_wkt = raster_utils.get_dataset_projection_wkt_uri(raster_uri) 
   
    # Temporary filename for an intermediate step
    aoi_reprojected_uri = raster_utils.temporary_filename()

    # Reproject the AOI to the spatial reference of the raster so that the
    # AOI can be used to clip the raster properly
    raster_utils.reproject_datasource_uri(aoi, raster_wkt, aoi_reprojected_uri)

    # Temporary URI for an intermediate step
    clipped_uri = raster_utils.temporary_filename()

    LOGGER.debug('Clipping dataset')
    raster_utils.clip_dataset_uri(
            raster_uri, aoi_reprojected_uri, clipped_uri, False)
    
    # Get a point from the clipped data object to use later in helping
    # determine proper pixel size
    raster_gt = raster_utils.get_geotransform_uri(clipped_uri)
    point_one = (raster_gt[0], raster_gt[3])
   
    # Create a Spatial Reference from the rasters WKT
    raster_sr = osr.SpatialReference()
    raster_sr.ImportFromWkt(raster_wkt)
    
    # A coordinate transformation to help get the proper pixel size of
    # the reprojected raster
    coord_trans = osr.CoordinateTransformation(raster_sr, aoi_sr)
  
    pixel_size = raster_utils.pixel_size_based_on_coordinate_transform_uri(
            clipped_uri, coord_trans, point_one)

    LOGGER.debug('Reprojecting dataset')
    # Reproject the raster to the projection of the AOI
    raster_utils._experimental_reproject_dataset(
            clipped_uri, pixel_size[0], aoi_wkt, projected_uri)
    
    LOGGER.debug('Leaving clip_and_reproject_dataset')
    
def clip_and_reproject_shapefile(shapefile_uri, aoi_uri, projected_uri):
    """Clip and project a DataSource to an area of interest

        shapefile_uri - a URI to a ogr Datasource
        aoi_uri - a URI to a ogr DataSource of geometry type polygon
        projected_uri - a URI string for the output shapefile to be written to
            disk 

        returns - a DataSource clipped and projected to an area of interest"""

    LOGGER.debug('Entering clip_and_reproject_shapefile')
    # Get the AOIs spatial reference as strings in Well Known Text
    aoi_sr = raster_utils.get_spatial_ref_uri(aoi_uri)
    aoi_wkt = aoi_sr.ExportToWkt()

    # Get the Well Known Text of the shapefile
    shapefile_sr = raster_utils.get_spatial_ref(shapefile_uri)
    shapefile_wkt = shapefile_sr.ExportToWkt()
    
    # Temporary URI for an intermediate step
    aoi_reprojected_uri = raster_utils.temporary_filename()
    
    # Reproject the AOI to the spatial reference of the shapefile so that the
    # AOI can be used to clip the shapefile properly
    raster_utils.reproject_datasource_uri(
            aoi_uri, shapefile_wkt, aoi_reprojected_uri)

    # Temporary URI for an intermediate step
    clipped_uri = raster_utils.temporary_filename()
    
    # Clip the shapefile to the AOI
    LOGGER.debug('Clipping datasource')
    clip_datasource(aoi_reprojected_uri, shapefile_uri, clipped_uri)
    
    # Reproject the clipped shapefile to that of the AOI
    LOGGER.debug('Reprojecting datasource')
    raster_utils.reproject_datasource_uri(clipped_uri, aoi_wkt, projected_uri)
    
    LOGGER.debug('Leaving clip_and_reproject_maps')

def clip_datasource(aoi_uri, orig_ds_uri, output_uri):
    """Clip an OGR Datasource of geometry type polygon by another OGR Datasource
        geometry type polygon. The aoi should be a shapefile with a layer
        that has only one polygon feature

        aoi_uri - a URI to an OGR Datasource that is the clipping bounding box
        orig_ds_uri - a URI to an OGR Datasource to clip
        out_uri - output uri path for the clipped datasource

        returns - Nothing"""
   
    LOGGER.debug('Entering clip_datasource')

    aoi_ds = ogr.Open(aoi_uri)
    orig_ds = ogr.Open(orig_ds_uri)

    orig_layer = orig_ds.GetLayer()
    aoi_layer = aoi_ds.GetLayer()

    # If the file already exists remove it
    if os.path.isfile(output_uri):
        os.remove(output_uri)

    LOGGER.debug('Creating new datasource')
    # Create a new shapefile from the orginal_datasource 
    output_driver = ogr.GetDriverByName('ESRI Shapefile')
    output_datasource = output_driver.CreateDataSource(output_uri)

    # Get the original_layer definition which holds needed attribute values
    original_layer_dfn = orig_layer.GetLayerDefn()

    # Create the new layer for output_datasource using same name and geometry
    # type from original_datasource as well as spatial reference
    output_layer = output_datasource.CreateLayer(
            original_layer_dfn.GetName(), orig_layer.GetSpatialRef(), 
            original_layer_dfn.GetGeomType())

    # Get the number of fields in original_layer
    original_field_count = original_layer_dfn.GetFieldCount()

    LOGGER.debug('Creating new fields')
    # For every field, create a duplicate field and add it to the new 
    # shapefiles layer
    for fld_index in range(original_field_count):
        original_field = original_layer_dfn.GetFieldDefn(fld_index)
        output_field = ogr.FieldDefn(
                original_field.GetName(), original_field.GetType())
        # NOT setting the WIDTH or PRECISION because that seems to be unneeded
        # and causes interesting OGR conflicts
        output_layer.CreateField(output_field)

    # Get the feature and geometry of the aoi
    aoi_feat = aoi_layer.GetFeature(0)
    aoi_geom = aoi_feat.GetGeometryRef()
    
    LOGGER.debug('Starting iteration over geometries')
    # Iterate over each feature in original layer
    for orig_feat in orig_layer:
        # Get the geometry for the feature
        orig_geom = orig_feat.GetGeometryRef()
    
        # Check to see if the feature and the aoi intersect. This will return a
        # new geometry if there is an intersection. If there is not an
        # intersection it will return an empty geometry or it will return None
        # and print an error to standard out
        intersect_geom = aoi_geom.Intersection(orig_geom)
        
        if not intersect_geom == None and not intersect_geom.IsEmpty():
            # Copy original_datasource's feature and set as new shapes feature
            output_feature = ogr.Feature(
                    feature_def=output_layer.GetLayerDefn())
        
            # Since the original feature is of interest add it's fields and
            # Values to the new feature from the intersecting geometries
            # The False in SetFrom() signifies that the fields must match
            # exactly
            output_feature.SetFrom(orig_feat, False)
            output_feature.SetGeometry(intersect_geom)
            output_layer.CreateFeature(output_feature)
            output_feature = None
    
    LOGGER.debug('Leaving clip_datasource')
    output_datasource = None
