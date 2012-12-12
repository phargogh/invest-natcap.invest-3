''' This will be temporary until I can integrate these into the HRA core. It
will act as scratch space for a variety of functions.'''


def make_recovery_rast(dir, hab):

    raster_list = []
    sum_dq = 0

    for h in hab:
        sum = 0
        for crit in h['Crit_Ratings']:
            r = crit['Rating']
            dq = crit['DQ']

            sum += r/dq
            sum_dq += 1/dq
        #Burn all numeric criteria to a single raster so that it could be combined
        #with raster criteria after the fact.
        
        for crit in h['Crit_Rasters']
            dq = crit['DQ']

            sum_dq += 1/ dq
            
            #Burn r/dq to a new temporary raster so that it can be combined with the others,
            #then divided out over 1/dq once they're summed. Add to raster stack for later
            #vectorizing...again.
            old_band = crit['DS'].GetRasterBand(1)
            old_array = old_band.ReadAsArray()

            new_array = old_array / dq

            #Make a new raster here and burn the above array to it. Then add it to the stack.

            raster_list.append(new_ds)
    
    
def make_risk_rasters(dir, h_s, hab, stress, risk_eq):
    
    risk_rasters = {}
    denoms = {}

    for pair in h_s:
        
        h,s = pair     
        e_sum, c_sum = 0

        for sub_dict in (h_s[pair], hab[h]):
            for crit in (sub_dict['Crit_Ratings'], sub_dict['Crit_Rasters']):
                
                dq = crit['DQ']
                w = crit['Weight']

                c_sum += 1/(dq * w)
        
        denoms[pair]['C'] = c_sum

        for crit in (stress[s]['Crit_Ratings'], stress[s]['Crit_Rasters']):

            dq = crit['DQ']
            w = crit['Weight']

            e_sum += 1 / (dq * w)
        
        denoms[pair]['E'] = e_sum

    #At this point, denoms exists, and we can pass the particular one to the calc_C
    #and calc_E functions to rasterize.
    out_dir = os.path.join(dir, 'Temp_Calc_Rast')

    for pair in h_s:
        
        h, s = pair
       
        e_out_path = os.path.join(out_dir, h + s + 'E.tif')
        c_out_path = os.path.join(out_dir, h + s + 'C.tif')

        #E and C are both raster burned spatially explicit versions of E
        E = calc_E_value(h_s[pair]['DS'], stress[s], denoms[pair]['E'], e_out_path)
        C = calc_C_value(h_s[pair]['DS'], h_s[pair], hab[h], denoms[pair]['C'], c_out_path)

        r_ds = h_s[pair]['DS']
        r_band = r_ds.GetRasterBand(1)

        if risk_eq == 'Multiplicative':
            make_risk_mult(r_band, E, C, out_URI)
        elif risk_eq == 'Euclidean':
            make_risk_euc(r_band, E, C, out_URI)

def make_risk_euc(band, E, C, out_URI)
     
    layers = [band, E, C]

    #Know explicitly that this is the order the layers are passed in as.  
    def vec_euc(b_pixel, e_pixel, c_pixel):

        if e_pixel == 0 or b_pixel == 0:
            return 0

        e_pixel = e_pixel * b_pixel
        e_tot = (e_pixel - 1) ** 2
        c_tot = (c_pixel - 1) ** 2

        under_tot = e_tot + c_tot

        return math.sqrt(under_tot)

    #Vectorize raster using the layers list, and the vec_euc function

def calc_E_value(ds, s_dicts, denom, out_path):

    new_ds = raster_utils.new_raster_from_base(ds, out_path, 'GTiff', 0,
                                gdal.GDT_Float32)
    band, nodata = raster_utils.extract_band_and_nodata(new_ds)
    band.Fill(nodata)

    e_num = 0
    for crit in s_dicts['Crit_Ratings']:
        
        dq = crit['DQ']
        w = crit['Weight']
        r = crit['Rating']

        e_num += r / (dq * w)

    def e_combine(*pixels):
        
        p_sum = o

        for p in pixels:
            sum += p
        p_sum += e_num

        return e_num / denom

    raster_list = []
    for crit in s_dicts['Crit_Rasters']:
        raster_list.append(crit['DS'])
    
    #vectorize using the raster band as the base, and all potential rasters on top of that.

def make_risk_mult(band, E, C, out_URI):

    
