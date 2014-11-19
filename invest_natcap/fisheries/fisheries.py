'''
The Fisheries module contains the high-level code for excuting the fisheries
model
'''

import logging

import fisheries_io as io
import fisheries_model as model

import pprint as pp

from matplotlib import pyplot as plt
import numpy as np

LOGGER = logging.getLogger('FISHERIES')
logging.basicConfig(format='%(asctime)s %(name)-15s %(levelname)-8s \
    %(message)s', level=logging.DEBUG, datefmt='%m/%d/%Y %H:%M:%S ')


def execute(args):
    '''
    Entry point into the Fisheries Model

    Args:
        workspace_dir (string): location into which all intermediate and
            output files should be placed.

        aoi_uri (string): location of shapefile which will be used as
            subregions for calculation. Each region must conatin a 'name'
            attribute which will

        timesteps(int): represents the number of time steps that
            the user desires the model to run.

        population_type (string): specifies whether the model
            is age-specific or stage-specific. Options will be either "Age
            Specific" or "Stage Specific" and will change which equation is
            used in modeling growth.

        sexsp (string): specifies whether or not the age and stage
            classes are distinguished by sex.

        population_csv_uri (string): location of the population parameters
            csv. This will contain all age and stage specific parameters.

        spawn_units (string):

        total_init_recruits (float): represents the initial number of
            recruits that will be used in calculation of population on a per
            area basis.

        recruitment_type (string):

        alpha (float): must exist within args for BH or Ricker.
            Parameter that will be used in calculation of recruitment.

        beta (float): must exist within args for BH or Ricker.
            Parameter that will be used in calculation of recruitment.

        total_recur_recruits (float): must exist within args for Fixed.
            Parameter that will be used in calculation of recruitment.

        migr_cont (bool): if true, model uses migration

        migration_dir (string): if this parameter exists, it means
            migration is desired. This is  the location of the parameters
            folder containing files for migration. There should be one file for
            every age class which migrates.

        harv_cont (bool): if true, model runs harvest computations

        harvest_units (string): specifies how the user wants to get
            the harvest data. Options are either "Individuals" or "Weight", and
            will change the harvest equation used in core.

        frac_post_process (float): represents the fraction of the animal
            remaining after processing of the whole carcass is complete.
            This will exist only if valuation is desired for the particular
            species.

        unit_price (float): represents the price for a single unit of
            harvest. Exists only if valuation is desired.

    Example Args Dictionary::

        {
            'workspace_dir': 'path/to/workspace_dir',
            'aoi_uri': 'path/to/aoi_uri',
            'total_timesteps': 100,
            'population_type': 'Stage-Based',
            'sexsp': 'Yes',
            'population_csv_uri': 'path/to/csv_uri',
            'spawn_units': 'Weight',
            'total_init_recruits': 100.0,
            'recruitment_type': 'Ricker',
            'alpha': 32.4,
            'beta': 54.2,
            'total_recur_recruits': 92.1,
            'migr_cont': True,
            'migration_dir': 'path/to/mig_dir',
            'harv_cont': True,
            'harvest_units': 'Individuals',
            'frac_post_process': 0.5,
            'unit_price': 5.0,
        }
    '''

    # Parse Inputs
    vars_dict = io.fetch_verify_args(args)

    # Setup Model
    vars_dict = model.initialize_vars(vars_dict)

    recru_func = model.set_recru_func(vars_dict)
    init_cond_func = model.set_init_cond_func(vars_dict)
    cycle_func = model.set_cycle_func(vars_dict, recru_func)
    harvest_func = model.set_harvest_func(vars_dict)

    # Run Model
    vars_dict = model.run_population_model(
        vars_dict, init_cond_func, cycle_func, harvest_func)

    # Generate Outputs
    io.generate_outputs(vars_dict)
