import numpy as np
import data_handler
import carbon_seq
import osgeo.gdal
import osgeo.osr as osr
from dbfpy import dbf

def execute(args):
    """Executes the basic carbon model that maps a carbon pool dataset to a
        LULC raster.
    
        args - is a dictionary with at least the following entries:
        args['lulc_cur'] - is a GDAL raster dataset
        args['lulc_fut'] - is a GDAL raster dataset
        args['carbon_pools'] - is a DBF dataset mapping carbon sequestration numbers to lulc classifications.
        args['seq_cur'] - a GDAL raster dataset for outputing the sequestered carbon
                          based on the current lulc
        args['seq_fut'] - a GDAL raster dataset for outputing the sequestered carbon
                          based on the future lulc
        args['seq_delta'] - a GDAL raster dataset for outputing the difference between
                            args['seq_cur'] and args['seq_fut']
        args['seq_value'] - a GDAL raster dataset for outputing the monetary gain or loss in
                            value of sequestered carbon.
        args['calc_value'] - is a Boolean.  True if we wish to perform valuation.
        
        returns nothing"""

    if args['calc_value']:
        valuate(args)
    else:
        sequester(args)
    

def sequester(args):
    """Executes the carbon sequestration model only.
    
        args - is a dictionary with at least the following entries:
        args['lulc_cur'] - is a GDAL raster dataset
        args['seq_cur'] - is a GDAL raster dataset
        args['carbon_pools'] - is a DBF dataset mapping sequestration numbers to lulc classifications
        
        returns a constructed pools dict mapping lulc types to total carbon sequestered per type (Mg/Ha)"""

    pools = build_pools(args['carbon_pools'], args['lulc_cur'], args['seq_cur'])

    rasterSeq(pools, args['lulc_cur'], args['seq_cur'])


def valuate(args):
    pools = build_pools(args['carbon_pools'], args['lulc_cur'], args['seq_cur'])
    
    rasterSeq(pools, args['lulc_cur'], args['seq_cur'])
    rasterSeq(pools, args['lulc_fut'], args['seq_fut'])
    

def rasterSeq(pools, inputRaster, outputRaster):
    lulc = inputRaster.GetRasterBand(1)
    for i in range(0, lulc.YSize):
        data = lulc.ReadAsArray(0, i, lulc.XSize, 1)
        out_array = carbon_seq.execute(data, pools)
        outputRaster.GetRasterBand(1).WriteArray(out_array, 0, i)

def rasterDiff(pools, lulc_cur, lulc_fut, outputRaster):
    lulc_cur_band = lulc_cur.GetRasterBand(1)
    lulc_fut_band = lulc_fut.GetRasterBand(1)
    for i in range(0, lulc_cur_band.YSize):
        cur_data = lulc_cur_band.ReadAsArray(0, i, lulc_cur_band.XSize, 1)
        fut_data = lulc_fut_band.ReadAsArray(0, i, lulc_cur_band.XSize, 1)
        out_array = carbon_seq.execute(pools, cur_data, fut_data)
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

def build_pools(dbf, inputRaster, outputRaster):
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
