'''
The Crop Production module contains the high-level code for excuting the Crop
Production model
'''

import logging
import pprint as pp

import crop_production_io as io
import crop_production_model as model

LOGGER = logging.getLogger('CROP_PRODUCTION')
logging.basicConfig(format='%(asctime)s %(name)-15s %(levelname)-8s \
    %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')


def execute(args, create_outputs=True):
    '''
    Entry point into the Crop Production Model

    :param str args['workspace_dir']: location into which all intermediate
        and output files should be placed.

    :param str args['results_suffix']: a string to append to output filenames

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    :param str args['']:

    Example Args::

        args = {
            'workspace_dir': 'path/to/workspace_dir/',
            'results_suffix': 'scenario_name',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
            '': '',
        }

    '''

    # Parse Inputs
    vars_dict = io.fetch_args(args, create_outputs=create_outputs)

    # Run Model ...

    # Calculate Yield
    if vars_dict['do_yield_observed']:
        vars_dict = model.calc_yield_observed(vars_dict)

    if vars_dict['do_climate_based_yields']:

        if vars_dict['do_yield_percentile']:
            vars_dict = model.calc_yield_percentile(vars_dict)

        if vars_dict['do_yield_modeled']:
            vars_dict = model.calc_yield_modeled(vars_dict)

    # Calculate Nutrition
    if vars_dict['do_nutrition']:
        vars_dict = model.calc_nutrition(vars_dict)

    # Calculate Economic Returns
    if vars_dict['do_economic_returns']:
        vars_dict = model.calc_economic_returns(vars_dict)

    # Return Results
    return vars_dict
