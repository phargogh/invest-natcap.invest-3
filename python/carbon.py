#carbon.py
#
#Extract the arguments of the Geoprocessing Object to a Python Dictionary

import sys, string, os, arcgisscripting, math, time, datetime, re, invest_core.uri_carbon

gp = arcgisscripting.create()

testParameter = gp.GetParameterAsText(0)
lulc_uri      = gp.GetParameterAsText(1)
pool_uri      = gp.GetParameterAsText(2)
output_uri    = gp.GetParameterAsText(3)

lulc_dictionary   = {'uri'  : lulc_uri,
                     'type' :'gdal',
                     'input': True}

pool_dictionary   = {'uri'  : pool_uri}

output_dictionary = {'uri'  : output_uri,
                     'type' : 'gdal',
                     'input': False}


arguments = {'lulc': lulc_dictionary,
             'carbon_pools' : pool_dictionary,
             'output' : output_dictionary}

uri_carbon(arguments)

gp.addmessage("done.")
