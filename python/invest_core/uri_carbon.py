import numpy as np
import gdal
import carbon


def uri_carbon(in_args):
    #preprocess in_args
    out_args = {}
    for key,value in args.iteritems():
        if type(value) == 'dict':
            #probably need to process a gdal object hee
            out_args[key] = dst_ds = driver.Create( value[uri], 10, 10, 1, gdal.GDT_Byte )
        else:
            out_args[key] = value
            
    #invoke core function
    carbon.carbon(args)
    
    #process any return result (save to disk)
    print 'TODO: save stuff'