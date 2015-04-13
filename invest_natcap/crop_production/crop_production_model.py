'''
The Crop Production Model module contains functions for running the model
'''

import os
import logging
import pprint
import gdal

from raster import Raster, RasterFactory
from vector import Vector
import pygeoprocessing.geoprocessing as pygeo

LOGGER = logging.getLogger('CROP_PRODUCTION')
logging.basicConfig(format='%(asctime)s %(name)-15s %(levelname)-8s \
    %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')

pp = pprint.PrettyPrinter(indent=4)


def create_yield_func_output_folder(vars_dict, folder_name):
    '''
    Example Returns::

        vars_dict = {
            # ...

            'output_yield_func_dir': '/path/to/outputs/yield_func/',
            'output_production_maps_dir': '/path/to/outputs/yield_func/production/'
        }

    Output:
        .
        |-- [yield_func]_[results_suffix]
            |-- production

    '''
    if vars_dict['results_suffix']:
        folder_name = folder_name + '_' + vars_dict['results_suffix']
    output_yield_func_dir = os.path.join(vars_dict['output_dir'], folder_name)
    if not os.path.exists(output_yield_func_dir):
        os.makedirs(output_yield_func_dir)
    vars_dict['output_yield_func_dir'] = output_yield_func_dir

    if vars_dict['create_crop_production_maps']:
        output_production_maps_dir = os.path.join(
            output_yield_func_dir, 'crop_production_maps')
        if not os.path.exists(output_production_maps_dir):
            os.makedirs(output_production_maps_dir)
        vars_dict['output_production_maps_dir'] = output_production_maps_dir

    return vars_dict


def calc_observed_yield(vars_dict):
    '''
    Creates yield maps from observed data and stores in the temporary yield
        folder

    Args:
        vars_dict (dict): descr

    Example Args::

        vars_dict = {
            # ...

            'lulc_map_uri': '/path/to/lulc_map_uri',
            'crop_lookup_dict': {
                'code': 'crop_name',
                ...
            },
            'observed_yields_maps_dict': {
                'crop': '/path/to/crop_climate_bin_map',
                ...
            },
            'economics_table_dict': {
                'crop': 2.3,
                ...
            },
        }
    '''
    # pp.pprint(vars_dict)
    vars_dict = create_yield_func_output_folder(
        vars_dict, "observed_yield")

    crop_production_dict = {}
    lulc_raster = Raster.from_file(vars_dict['lulc_map_uri'])
    aoi_vector = Vector.from_shapely(
        lulc_raster.get_aoi(), lulc_raster.get_projection())
    economics_table = vars_dict['economics_table_dict']

    # setup useful base rasters
    base_raster_float = lulc_raster.set_datatype(gdal.GDT_Float32)
    base_raster_float_neg1 = base_raster_float.set_nodata(-1)
    base_raster_zeros_float_neg1 = base_raster_float_neg1.zeros()
    base_raster_ones_float_neg1 = base_raster_zeros_float_neg1.ones()

    print base_raster_float_neg1
    print base_raster_zeros_float_neg1
    print base_raster_ones_float_neg1
    return

    ### NEED TO REWORK RASTERS BELOW

    if vars_dict['do_economic_returns']:
        revenue_raster = zero_float_raster.copy()

    for crop in vars_dict['observed_yields_maps_dict'].keys():
        # Wrangle Data...
        crop_observed_yield_raster = Raster.from_file(
            vars_dict['observed_yields_maps_dict'][crop])

        reproj_aoi_vector = aoi_vector.reproject(
            crop_observed_yield_raster.get_projection())

        clipped_crop_raster = crop_observed_yield_raster.clip(
            reproj_aoi_vector.uri)

        # print clipped_crop_raster
        # continue

        if clipped_crop_raster.get_shape() == (1, 1):
            observed_yield_val = float(clipped_crop_raster.get_band(1).data[0, 0])
            aligned_crop_raster = revenue_raster.ones() * observed_yield_val
        else:
            # this reprojection could result in very long computation times
            reproj_crop_raster = clipped_crop_raster.reproject(
                lulc_raster.get_projection(), 'nearest', lulc_raster.get_affine().a)

            aligned_crop_raster = reproj_crop_raster.align_to(
                revenue_raster, 'nearest')

        # print aligned_crop_raster
        # continue

        crop_lookup_dict = vars_dict['crop_lookup_dict']
        inv_crop_lookup_dict = {v: k for k, v in crop_lookup_dict.items()}
        
        # print inv_crop_lookup_dict
        # continue

        reclass_table = {}
        for key in vars_dict['observed_yields_maps_dict'].keys():
            reclass_table[inv_crop_lookup_dict[key]] = 0
        reclass_table[inv_crop_lookup_dict[crop]] = 1

        reclassed_lulc_raster = lulc_raster.reclass(reclass_table)
        masked_lulc_raster = zero_float_raster.set_nodata(
            aligned_crop_raster.get_nodata(1))

        print masked_lulc_raster * aligned_crop_raster
        continue

        # Operations as Noted in User's Guide...
        ha_per_m2 = 0.0001
        ObservedLocalYield_raster = masked_lulc_raster * aligned_crop_raster
        ha_per_cell = ObservedLocalYield_raster.get_cell_area() * ha_per_m2  # or pass units into raster method?
        Production_raster = ObservedLocalYield_raster * ha_per_cell

        # print Production_raster

        if vars_dict['create_crop_production_maps']:
            filename = crop + '_production_map.tif'
            dst_uri = os.path.join(vars_dict[
                'output_production_maps_dir'], filename)
            Production_raster.save_raster(dst_uri)

        ProductionTotal_float = Production_raster.get_band(1).sum()
        crop_production_dict[crop] = ProductionTotal_float

        # print crop_production_dict

        if vars_dict['do_economic_returns']:
            revenue_raster += _calc_crop_revenue(
                Production_raster,
                economics_table[crop])

        print revenue_raster

        # Clean Up Rasters...
        del crop_observed_yield_raster
        del clipped_crop_raster
        del reproj_crop_raster
        del aligned_crop_raster
        del reclassed_lulc_raster
        del ObservedLocalYield_raster
        del Production_raster

    # vars_dict['crop_production_dict'] = crop_production_dict

    # # Economics map
    # if vars_dict['do_economic_returns']:
    #     cost_per_ton_input_raster = 0
    #     if vars_dict['modeled_fertilizer_maps_dir']:
    #         cost_per_ton_input_raster = _calc_cost_of_per_ton_inputs(
    #             vars_dict, lulc_raster)

    #     cost_per_hectare_input_raster = _calc_cost_of_per_hectare_inputs()

    #     cost_raster = cost_per_hectare_input_raster + cost_per_ton_input_raster
    #     economic_returns_raster = revenue_raster - cost_raster

    #     economic_returns_map_uri = os.path.join(
    #         vars_dict['output_yield_func_dir'], 'economic_returns_map.tif')
    #     economic_returns_raster.save_raster(economic_returns_map_uri)

    #     del economic_returns_raster
    #     del cost_per_ton_input_raster
    #     del cost_per_hectare_input_raster
    #     del cost_raster
    #     del revenue_raster

    # # Results Table
    # create_results_table(vars_dict)

    return vars_dict


def _calc_crop_revenue(production_raster, economics_table):
    '''
    Revenue_crop = Production_crop * Price_crop
    '''
    pass


def _calc_cost_of_per_ton_inputs(revenue_raster, fert_maps_dict, economics_table_crop):
    '''
    sum_across_fert(FertAppRate_fert * LULCCropCellArea * CostPerTon_fert)
    '''
    CostPerTonInputTotal_raster = revenue_raster * 0
    try:
        cost_nitrogen_per_ton = economics_table_crop['cost_nitrogen_per_ton']
        Nitrogen_raster = Raster.from_file(fert_maps_dict['nitrogen'])
        NitrogenCost_raster = Nitrogen_raster * cost_nitrogen_per_ton
        CostPerTonInputTotal_raster += NitrogenCost_raster
    except:
        pass
    try:
        cost_phosphorous_per_ton = economics_table_crop['cost_phosphorous_per_ton']
        PhosphorousCost_raster = Phosphorous_raster * cost_phosphorous_per_ton
        CostPerTonInputTotal_raster += PhosphorousCost_raster
    except:
        pass
    try:
        cost_potash_per_ton = economics_table_crop['cost_potash_per_ton']
        Potash_raster = Raster.from_file(fert_maps_dict['potash'])
        PotashCost_raster = Potash_raster * cost_potash_per_ton
        CostPerTonInputTotal_raster += PotashCost_raster
    except:
        pass

    return CostPerTonInputTotal_raster


def _calc_cost_of_per_hectare_inputs():
    '''

    '''
    pass

def _calc_returns():
    '''
    Cost_crop = CostPerTonTotalInput_crop + CostPerHectareInputTotal_crop
    Returns_crop = Revenue_crop - Cost_crop

    '''


def calc_percentile_yield(vars_dict):
    '''
    Example Args::

        vars_dict = {
            ...

            '': '',
        }
    '''
    vars_dict = create_yield_func_output_folder(
        vars_dict, "climate_percentile_yield")
    pass


def calc_regression_yield(vars_dict):
    '''
    Example Args::

        vars_dict = {
            ...

            '': '',
        }
    '''
    vars_dict = create_yield_func_output_folder(
        vars_dict, "climate_regression_yield")
    pass


def calc_economic_returns(crop_production_raster, crop_economics_dict):
    '''
    '''

    # per ton
    price = crop_economics_dict['price']

    cost_nitrogen = crop_economics_dict['cost_nitrogen']
    cost_phosphorous = crop_economics_dict['cost_phosphorous']
    cost_potash = crop_economics_dict['cost_potash']

    # per hectare
    cost_labor = crop_economics_dict['cost_labor']
    cost_machine = crop_economics_dict['cost_machine']
    cost_seed = crop_economics_dict['cost_seed']
    cost_irrigation = crop_economics_dict['cost_irrigation']

    # 
    crop_returns_raster = crop_production_raster
    economic_returns_raster = economic_returns_raster_next


def create_results_table(vars_dict):
    '''
    Example Args::

        vars_dict = {
            ...

            'crop_production_dict': {
                'corn': 12.3,
                'soy': 13.4,
                ...
            },
            '': '',
        }
    '''
    pass
