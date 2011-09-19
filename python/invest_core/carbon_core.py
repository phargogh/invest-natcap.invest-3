import numpy as np
import data_handler
import carbon_seq
import carbon_diff
import carbon_value
import carbon_add
import osgeo.gdal
from osgeo import gdal
import osgeo.osr as osr
from osgeo import ogr
from dbfpy import dbf
import math

def execute(args):
    """Executes the basic carbon model that maps a carbon pool dataset to a
        LULC raster.
    
        args - is a dictionary with at least the following entries:
        args['lulc_cur'] - is a GDAL raster dataset
        args['lulc_fut'] - is a GDAL raster dataset
        args['carbon_pools'] - is a DBF dataset mapping carbon sequestration numbers to lulc classifications.
        args['storage_cur'] - a GDAL raster dataset for outputing the sequestered carbon
                          based on the current lulc
        args['storage_fut'] - a GDAL raster dataset for outputing the sequestered carbon
                          based on the future lulc
        args['seq_delta'] - a GDAL raster dataset for outputing the difference between
                            args['storage_cur'] and args['storage_fut']
        args['seq_value'] - a GDAL raster dataset for outputing the monetary gain or loss in
                            value of sequestered carbon.
        args['calc_value'] - is a Boolean.  True if we wish to perform valuation.
        args['lulc_cur_year'] - is an int.  Represents the year of lulc_cur
        args['lulc_fut_year'] - is an int.  Represents the year of lulc_fut
        args['c_value'] - a float.  Represents the price of carbon in US Dollars.
        args['discount'] - a float.  Represents the annual discount in the price of carbon
        args['rate_change'] - a float.  Represents the rate of change in the price of carbon
        
        returns nothing"""

    #Calculate the per pixel carbon storage due to lulc pools
    area = pixelArea(args['lulc_cur'])
    inNoData = args['lulc_cur'].GetRasterBand(1).GetNoDataValue()
    outNoData = args['storage_cur'].GetRasterBand(1).GetNoDataValue()
    pools = build_pools_dict(args['carbon_pools'], area, inNoData, outNoData)

    #calculate carbon storage
    rasterSeq(pools, args['lulc_cur'], args['storage_cur'])
    if 'lulc_fut' in args:
        rasterSeq(pools, args['lulc_fut'], args['storage_fut'])
        #calculate sequestration
        rasterDiff(args['storage_cur'], args['storage_fut'], args['seq_delta'])

    if 'hwp_cur_shape' in args:
        harvestProducts(args)

    if args['calc_value']:
        valuate(args)
        
    #close all datasets
    for key in args:
        args[key] = None
        
def harvestProducts(args):
    """Adds carbon due to harvested wood products
    
        args - is a dictionary with at least the following entries:
        args['lulc_cur'] - is a GDAL raster dataset
        args['storage_cur'] - is a GDAL raster dataset
        args['carbon_pools'] - is a DBF dataset mapping sequestration numbers to lulc classifications
        
        No return value."""
        
    #Make a copy of the hwp_cur_shape shape so we can write to it
    calculated_carbon_ds = ogr.GetDriverByName("Memory").\
                    CopyDataSource(args['hwp_cur_shape'], "")
    calculated_carbon_layer = calculated_carbon_ds.GetLayerByName('harv_samp_cur')
    
    #Create a hardwood products pool that will get calculated later
    hwp_def = ogr.FieldDefn("hwp_pool", ogr.OFTReal)
    calculated_carbon_layer.CreateField(hwp_def)
    
    #calculate hwp pools per feature
    for feature in calculated_carbon_layer:
        #First initialize the fields by index
        fieldArgs = {'Cut_cur' : feature.GetFieldIndex('Cut_cur'),
                     'Start_date' : feature.GetFieldIndex('Start_date'),
                     'Freq_cur' : feature.GetFieldIndex('Freq_cur'),
                     'Decay_cur' : feature.GetFieldIndex('Decay_cur'),
                     'C_den_cur' : feature.GetFieldIndex('C_den_cur'),
                     'BCEF_cur' : feature.GetFieldIndex('BCEF_cur')}
        
        #Then replace the indices with actual values
        for key,index in fieldArgs.iteritems():
            fieldArgs[key] = feature.GetField(index)
        

        #Apply equation #1 from the carbon user's guide
        limit = math.ceil((1.0/((args['lulc_cur_year']-fieldArgs['Start_date'])\
                                /fieldArgs['Freq_cur'])))
        sum = 0
        for t in range(int(limit)):
            w = math.log(2)/fieldArgs['Decay_cur']
            m = args['lulc_cur_year'] - fieldArgs['Start_date'] \
                    - (t*fieldArgs['Freq_cur'])
            sum += ((1-(math.e**(-w)))/(w*math.e**(m*w)))
            
        #set the HWP carbon pool for this feature.
        hwpCarbonPool = fieldArgs['Cut_cur']*sum
        hwpIndex = feature.GetFieldIndex('hwp_pool')
        feature.SetField(hwpIndex,hwpCarbonPool)
        calculated_carbon_layer.SetFeature(feature)
    
    #Make a new raster in memory for burning in the HWP values.
    driver = gdal.GetDriverByName("MEM")
    hwp_ds = driver.Create("temp.tif", args['lulc_cur'].RasterXSize,
                            args['lulc_cur'].RasterYSize, 1, gdal.GDT_Float32)
    hwp_ds.SetProjection(args['lulc_cur'].GetProjection())
    hwp_ds.SetGeoTransform(args['lulc_cur'].GetGeoTransform())
    hwp_ds.GetRasterBand(1).SetNoDataValue(-5.0)

    
    
    #Now burn the hwp pools into the HWP raster in memory.
    gdal.RasterizeLayer(hwp_ds,[1], calculated_carbon_layer,
                         options=['ATTRIBUTE=hwp_pool'])
    
    #Add the HWP raster to the storage raster, write the sum to the
    #storage raster.
    rasterAdd(args['storage_cur'], hwp_ds, args['storage_cur'])
    

def valuate(args):
    """Executes the economic valuation model.
        
        args is a dictionary with all of the options detailed in execute()
        
        No return value"""
        
    numYears = args['lulc_fut_year'] - args['lulc_cur_year']
    pools = build_pools(args['carbon_pools'], args['lulc_cur'], args['storage_cur'])
    rasterValue(args['seq_delta'], args['seq_value'], args['c_value'], args['discount'], args['rate_change'], numYears)
    
def rasterValue(inputRaster, outputRaster, carbonValue, discount, rateOfChange, numYears):
    """iterates through the rows in a raster and applies the carbon valuation model
        to all values.
        
        inputRaster - is a GDAL raster dataset
        outputRaster - is a GDAL raster dataset for outputing the value of carbon sequestered
        carbonValue - is a float representing the price of carbon per metric ton
        discount - is a float representing the market discount rate for Carbon
        rateOfChange - is a float representing the annual rate of change in the price of Carbon.
        numYears - an int representing the number of years between current and future land cover maps
        
        No return value."""
        
    nodataDict = build_nodata_dict(inputRaster, outputRaster)
    lulc = inputRaster.GetRasterBand(1)
    
    multiplier = 0.
#    for n in range(numYears-1): #Subtract 1 per the user's manual
    for n in range(numYears):    #This is incorrect, but it allows us to match the results of invest2
        multiplier += 1./(((1.+rateOfChange)**n)*(1.+discount)**n)
    
    for i in range(0, lulc.YSize):
        data = lulc.ReadAsArray(0, i, lulc.XSize, 1)
        out_array = carbon_value.execute(nodataDict, data, numYears, carbonValue, multiplier)
        outputRaster.GetRasterBand(1).WriteArray(out_array, 0, i)

def rasterSeq(pools, inputRaster, outputRaster):
    """Iterate through the rows in a raster and map carbon sequestration values
        to the output raster.
        
        pools - a python dict mapping lulc indices to sequestration data
        inputRaster - a GDAL raster dataset
        outputRaster - a GDAL raster dataset
        
        No return value."""
        
    lulc = inputRaster.GetRasterBand(1)
    for i in range(0, lulc.YSize):
        data = lulc.ReadAsArray(0, i, lulc.XSize, 1)
        out_array = carbon_seq.execute(data, pools)
        outputRaster.GetRasterBand(1).WriteArray(out_array, 0, i)

def rasterDiff(storage_cur, storage_fut, outputRaster):
    """Iterate through the rows in the two sequestration rasters and calculate the 
        difference in each pixel.  Maps the difference to the output raster.
        
        storage_cur - a GDAL raster dataset
        storage_fut - a GDAL raster dataset
        outputRaster - a GDAL raster dataset"""
    
    nodataDict = build_nodata_dict(storage_cur, outputRaster)
    lulc_cur_band = storage_cur.GetRasterBand(1)
    lulc_fut_band = storage_fut.GetRasterBand(1)
    for i in range(0, lulc_cur_band.YSize):
        cur_data = lulc_cur_band.ReadAsArray(0, i, lulc_cur_band.XSize, 1)
        fut_data = lulc_fut_band.ReadAsArray(0, i, lulc_cur_band.XSize, 1)
        out_array = carbon_diff.execute(nodataDict, cur_data, fut_data)
        outputRaster.GetRasterBand(1).WriteArray(out_array, 0, i)

def rasterAdd(storage_cur, hwpRaster, outputRaster):
    """Iterate through the rows in the two sequestration rasters and calculate the 
        sum of each pixel.  Maps the sum to the output raster.
        
        storage_cur - a GDAL raster dataset
        hwpRaster - a GDAL raster dataset
        outputRaster - a GDAL raster dataset"""
    
    nodataDict = build_nodata_dict(storage_cur, outputRaster)
    storage_band = storage_cur.GetRasterBand(1)
    hwp_band = hwpRaster.GetRasterBand(1)
    for i in range(0, storage_band.YSize):
        cur_data = storage_band.ReadAsArray(0, i, storage_band.XSize, 1)
        fut_data = hwp_band.ReadAsArray(0, i, storage_band.XSize, 1)
        out_array = carbon_add.execute(nodataDict, cur_data, fut_data)
        outputRaster.GetRasterBand(1).WriteArray(out_array, 0, i)

def pixelArea(dataset):
    """Calculates the pixel area of the given dataset.
    
        dataset - GDAL dataset
    
        returns area in Ha of each pixel in dataset"""

    srs = osr.SpatialReference()
    srs.SetProjection(dataset.GetProjection())
    linearUnits = srs.GetLinearUnits()
    geotransform = dataset.GetGeoTransform()
    #take absolute value since sometimes negative widths/heights
    areaMeters = abs(geotransform[1] * geotransform[5] * (linearUnits ** 2))
    return areaMeters / (10 ** 4) #convert m^2 to Ha

def build_nodata_dict(inputRaster, outputRaster):
    inNoData = inputRaster.GetRasterBand(1).GetNoDataValue()
    outNoData = outputRaster.GetRasterBand(1).GetNoDataValue()
    
    nodata = {'cur': inNoData, 'fut': outNoData}
    return nodata

def build_pools(dbf, inputRaster, outputRaster):
    """Extract the nodata values from the input and output rasters and build
        the carbon pools dict.
        
        dbf - an open DBF dataset
        inputRaster - a GDAL dataset (representing an LULC)
        outputRaster - a GDAL dataset
        
        returns a dictionary calculating total carbon sequestered per lulc type.
        """
    area = pixelArea(inputRaster)
    lulc = inputRaster.GetRasterBand(1)
    
    inNoData = lulc.GetNoDataValue()
    outNoData = outputRaster.GetRasterBand(1).GetNoDataValue()
    
    return build_pools_dict(dbf, area, inNoData, outNoData)

def build_pools_dict(dbf, area, inNoData, outNoData):
    """Build a dict for the carbon pool data accessible for each lulc classification.
    
        dbf - the database file describing pools
        area - the area in Ha of each pixel
        inNoData - the no data value for the input map
        outNoData - the no data value for the output map
    
        returns a dictionary calculating total carbon sequestered per lulc type"""

    poolsDict = {int(inNoData): outNoData}
    for i in range(dbf.recordCount):
        sum = 0
        for field in ('C_ABOVE', 'C_BELOW', 'C_SOIL', 'C_DEAD'):
            sum += dbf[i][field]
        poolsDict[dbf[i]['LULC']] = sum * area
    return poolsDict
