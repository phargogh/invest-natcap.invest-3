import os
import arcgisscripting
gp = arcgisscripting.create()
import subprocess

gp.AddMessage(os.path.dirname(os.path.realpath(__file__)))
os.chdir(os.path.dirname(os.path.realpath(__file__)))
gp.AddMessage(os.getcwd())

gp.AddMessage('Starting subprocess')
process = subprocess.Popen(['OSGeo4W\\gdal_python_exec.bat', 'python\import_tests.py'])
gp.AddMessage('Waiting')
process.wait()
gp.AddMessage('Done')
