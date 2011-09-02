#carbon_arc.py
import os, sys, subprocess

try:
    import json
except ImportError:
    import invest_core.simplejson as json

import arcgisscripting
gp = arcgisscripting.create()

os.chdir(os.path.dirname(os.path.realpath(__file__)) + "\\..\\")
gp.AddMessage(os.getcwd())

lulc_uri = gp.GetParameterAsText(0)
pool_uri = gp.GetParameterAsText(1)
output_filename = gp.GetParameterAsText(2)
output_dir = gp.GetParameterAsText(3)

lulc_dictionary = {'uri'  : lulc_uri,
                   'type' :'gdal',
                   'input': True}

pool_dictionary = {'uri'  : pool_uri,
                   'type': 'dbf',
                   'input': True}


#Data type codes (from http://www.gdal.org/gdal_8h.html):
# Enter one of these codes as the 'dataType' dict entry.  This will determine
# the data type of the output file.
#
# 0  = GDT_Unknown
# 1  = GDT_Byte
# 2  = GDT_UInt16
# 3  = GDT_Int16
# 4  = GDT_UInt32
# 5  = GDT_Int32
# 6  = GDT_Float32
# 7  = GDT_Float64
# 8  = GDT_CInt16
# 9  = GDT_CInt32
# 10 = GDT_CFloat32
# 11 = GDT_CFloat64

output_cur_seq = {'uri'  : output_dir + '\\current_sequestration.tif',
                     'type' : 'gdal',
                     'dataType': 6,
                     'input': False}

output_fut_seq = {'uri'  : output_dir + '\\future_sequestration.tif',
                     'type' : 'gdal',
                     'dataType': 6,
                     'input': False}

output_delta_seq = {'uri'  : output_dir + '\\delta_sequestration.tif',
                     'type' : 'gdal',
                     'dataType': 6,
                     'input': False}

output_valuation = {'uri'  : output_dir + '\\valuation.tif',
                     'type' : 'gdal',
                     'dataType': 6,
                     'input': False}

output_dictionary = {'cur_seq': output_cur_seq,
                     'fut_seq': output_fut_seq,
                     'delta_seq':output_delta_seq,
                     'valuation':output_valuation}

arguments = {'lulc': lulc_dictionary,
             'carbon_pools' : pool_dictionary,
             'output' : output_dictionary}

gp.AddMessage('Starting carbon model')

#process = subprocess.Popen(['OSGeo4W\\gdal_python_exec.bat',
#                            'python\\invest_core\\invest.py',
#                            'carbon_core', json.dumps(arguments)])
gp.AddMessage('Waiting')
#process.wait()

#gp.overwriteoutput = 1

#gp.AddToolbox("C:\Program Files\ArcGIS\Desktop10.0\ArcToolbox\Toolboxes\Data Management Tools.tbx")
#output_layer = "buffer_layer"
#output_buffer = "output_buffer"

#gp.Buffer_analysis('C:\\Users\\jadoug06\\Desktop\\lulc_samp_cur', output_layer, "1 DecimalDegrees", "FULL", "ROUND", "NONE", "")

#gp.MakeFeatureLayer(output_buffer, output_layer)
#gp.SetParameterAsText(0, output_layer)

gp.AddMessage('Done')
