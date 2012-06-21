import os, sys
from poster.encode import multipart_encode
from poster.streaminghttp import register_openers
import urllib2


def execute(args):
    aoiFileName = args["aoiFileName"]
    cellSize = args["cellSize"]
    workspace_dir = args["workspace_dir"]
    
    dirname=os.path.dirname(aoiFileName)+os.sep
    fileName=os.path.basename(aoiFileName).strip(".shp") 
    aoiFileNameSHP = dirname+fileName+".shp"
    aoiFileNameSHX = dirname+fileName+".shx"
    aoiFileNameDBF = dirname+fileName+".dbf"
    aoiFileNamePRJ = dirname+fileName+".prj"
    
    # Register the streaming http handlers with urllib2
    register_openers()
    
    # Start the multipart/form-data encoding of the file "DSC0001.jpg"
    # "image1" is the name of the parameter, which is normally set
    # via the "name" parameter of the HTML <input> tag.
    
    # headers contains the necessary Content-Type and Content-Length
    # datagen is a generator object that yields the encoded parameters
    datagen, headers = multipart_encode({"aoiSHP": open(aoiFileNameSHP, "rb"),
                                         "aoiSHX": open(aoiFileNameSHX, "rb"),
                                         "aoiDBF": open(aoiFileNameDBF, "rb"),
                                         "aoiPRJ": open(aoiFileNamePRJ, "rb"),
                                         "cellSize": cellSize})
    
    # Create the Request object
    request = urllib2.Request("http://ncp-skookum.stanford.edu/~mlacayo/recreation.php", datagen, headers)
    
    # Actually do the request, and get the response
    # This will display the output from the model including the path for the results
    results = eval(urllib2.urlopen(request).read())
    url = "http://ncp-skookum.stanford.edu/~mlacayo/data/"+results["sessid"].strip()

    req = urllib2.urlopen(url)
    CHUNK = 16 * 1024
    with open(workspace_dir+os.sep+"results.zip", 'wb') as fp:
      while True:
        chunk = req.read(CHUNK)
        if not chunk: break
        fp.write(chunk)