#timber_arc.py
import os, sys, subprocess
import getpass
import json

import arcgisscripting
gp = arcgisscripting.create()

os.chdir(os.path.dirname(os.path.realpath(__file__)) + "\\..\\")

#build up the JSON dictionary for saving previously used parameters to disk.
arguments = {'output_dir': gp.GetParameterAsText(0),
             'lulc_cur_uri': gp.GetParameterAsText(1),
             'plant_prod_uri': gp.GetParameterAsText(2),
             'market_disc_rate': float(gp.GetParameterAsText(3))}

args_file = open('C:\Users\\' + getpass.getuser() + '\My Documents\ArcGIS\timber_args.json', 'w')
args_file.writelines(json.dumps(arguments))
args_file.close()

gp.AddMessage('Starting timber model')

process = subprocess.Popen(['OSGeo4W\\gdal_python_exec.bat',
                            'python\\invest_core\\invest_timber_core.py',
                            json.dumps(arguments)],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT).communicate()[0]

gp.AddMessage(process)
gp.AddMessage('Done')
