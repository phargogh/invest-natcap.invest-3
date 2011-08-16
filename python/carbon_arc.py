#carbon_arc.py
#
#Extract the arguments of the Geoprocessing Object to a Python Dictionary

import sys, string, os, arcgisscripting, math, time, datetime, re, invest_core.carbon_uri

gp = arcgisscripting.create()

def getParameters(index, gp):
    return gp.GetParameterAsText(index)


def carbon_arc(gp):
    lulc_uri = gp.GetParameterAsText(0)
    pool_uri = gp.GetParameterAsText(1)
    output_uri = gp.GetParameterAsText(2)

    lulc_dictionary = {'uri'  : lulc_uri,
                         'type' :'gdal',
                         'input': True}

    pool_dictionary = {'uri'  : pool_uri}

    output_dictionary = {'uri'  : output_uri,
                         'type' : 'gdal',
                         'input': False}


    arguments = {'lulc': lulc_dictionary,
                 'carbon_pools' : pool_dictionary,
                 'output' : output_dictionary}

    carbon_uri(arguments)
