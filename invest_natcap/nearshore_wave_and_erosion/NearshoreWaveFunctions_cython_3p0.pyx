import sys
import os
import csv
from math import *
import h5py
import copy
import warnings

import string, time, datetime, json
from datetime import datetime

cimport numpy as num
import numpy as num
from scipy import optimize
from scipy import stats
from scipy import interpolate
from pylab import *
from pylab import find
from matplotlib import *
import fpformat, operator

import cython
from cython.operator import dereference as deref
from libc.math cimport atan2
from libc.math cimport sin
from libc.math cimport sqrt
from libc.math cimport log

cdef extern from "stdlib.h":
    void* malloc(size_t size)
    void free(void* ptr)

g=9.81

def smooth(x,int window_len=11,window='hanning'):
    """smooth the data using a window with requested size.
    
    This method is based on the convolution of a scaled window with the signal.
    The signal is prepared by introducing reflected copies of the signal 
    (with the window size) in both ends so that transient parts are minimized
    in the begining and end part of the output signal.
    
    input:
        x: the input signal 
        window_len: the dimension of the smoothing window; should be an odd integer
        window: the type of window from 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'
            flat window will produce a moving average smoothing.

    output:
        the smoothed signal
        
    example:

    t=linspace(-2,2,0.1)
    x=sin(t)+randn(len(t))*0.1
    y=smooth(x)
    
    see also: 
    
    numpy.hanning, numpy.hamming, numpy.bartlett, numpy.blackman, numpy.convolve
    scipy.signal.lfilter
 
    TODO: the window parameter could be the window itself if an array instead of a string   
    """

    if x.ndim != 1:
        raise ValueError, "smooth only accepts 1 dimension arrays."

    if x.size < window_len:
        raise ValueError, "Input vector needs to be bigger than window size."


    if window_len<3:
        return x


    if not window in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
        raise ValueError, "Window is one of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'"


    s=numpy.r_[2*x[0]-x[window_len-1::-1],x,2*x[-1]-x[-1:-window_len:-1]]
    #print(len(s))
    if window == 'flat': #moving average
        w=numpy.ones(window_len,'d')
    else:
        w=eval('numpy.'+window+'(window_len)')

    y=numpy.convolve(w/w.sum(),s,mode='same')
    return y[window_len:-window_len+1]


def Fast_k(T,h):
    g=9.81;
    if type(h) is list:
        h=array(h)
    else:
        muo=4.0*pi**2*h/(g*T**2) 
        expt=1.55+1.3*muo+0.216*muo**2
        Term=1.0+muo**1.09*num.exp(-expt) 
        mu=muo*Term/num.sqrt(num.tanh(muo))
        k=mu/h 
        n=.5*(1.0+(2.0*k*h/sinh(2.0*k*h)))
        C=2*pi/T/k
        Cg=C*n ; #Group velocity
        
        if type(n) is numpy.ndarray:
            out=h<.05
            k[out]=nan;C[out]=nan;Cg[out]=nan
        
    return k,C,Cg

def gradient2(U,z):
    #dU=gradient2(U,z)    
    lz=len(z);dU=U*0;
    dU[0]=(U[1]-U[0])/(z[1]-z[0]);
    for uu in range(1,lz-1,1):
        dU[uu]=0.5*(U[uu+1]-U[uu])/(z[uu+1]-z[uu])+0.5*(U[uu]-U[uu-1])/(z[uu]-z[uu-1])
    dU[lz-1]=(U[lz-1]-U[lz-2])/(z[lz-1]-z[lz-2]);
    return dU
#End of Gradient2

def   WaveRegenWindCD(Xnew,bath_sm,Surge,Ho,To,Uo,Cf,Sr,PlantsPhysChar):
    # x: Vector of consecutive cross-shore positions going shoreward
    # h: Vector of water depths at the corresponding cross-shore position
    # Ho: Initial wave height to be applied at the first cross-shore position
    # To: Wave Period
    # Roots: An num.array of physical properties (density, diameter, and height) of mangrove roots at the corresponding cross-shore position (all zeros if mangroves don't exist at that location)
    # Trunk: An num.array of physical properties (density, diameter, and height) of mangrove trunks or the marsh or seagrass plants at the corresponding cross-shore position (all zeros if vegetation don't exist at that location)
    # Canop: An num.array of physical properties (density, diameter, and height) of the mangrove canopy at the corresponding cross-shore position (all zeros if mangroves don't exist at that location)
    # ReefLof: Location of reef
    
    
    # constants
    g=9.81;rho=1024.0;B=1.0;Beta=0.05;
    lxo=len(Xnew);dx=num.diff(Xnew);dx=abs(dx)
    factor=3.0**(-2);
    
    #Compute wind reduction factor and reduce surge
    zo=num.zeros(lxo)
    S=num.zeros(lxo)
    temp=find(Sr==7)#Marshes
    if temp.any():
        zo[temp]=0.11
        S[temp]=SurgeReduction(SurgeRed[temp])
    temp=find(Sr==8)#mangroves
    if temp.any():
        zo[temp]=0.55
        S[temp]=SurgeReduction(SurgeRed[temp])
    
    #bathymetry
    ho=num.array(-bath_sm+S)
    out=find(ho<.05);
    if out.any():
        out=out[0]
    else:
        out=len(ho)
    h=ho[0:out-1]
    Xnew=num.array(Xnew)
    x=Xnew[0:out-1];
    lx=len(x)
    
    #Create wind vector
    if Uo<>0:
        Cd_airsea=(1.1+0.035*Uo)*1e-3;
        Zo_marine=0.018*Cd_airsea*Uo**2*1.0/g;#Roughness water
        Zo=[max(Zo_marine,zo[ii]-h[ii]/30) for ii in range(lx)] #Reduction in roughness b/c veg. underwater
        Zo=num.array(Zo)
        fr=(Zo/Zo_marine)**0.0706*log(10*1.0/Zo)/log(10*1.0/Zo_marine);#Reduction factor
        U=fr*Uo;
    else:
        U=num.zeros(lx)+.0001;
    Ua=0.71*U**1.23;
    
    # Vegetation characteristics
    Roots=PlantsPhysChar['Roots']
    hRoots=Roots['RootHeight'];
    NRoots=Roots['RootDens']
    dRoots=Roots['RootDiam']
    CdR=Roots['RootCd']
    
    Trunks=PlantsPhysChar['Trunks']
    hTrunk=Trunks['TrunkHeight'];
    NTrunk=Trunks['TrunkDens']
    dTrunk=Trunks['TrunkDiam']
    CdT=Trunks['TrunkCd']
    
    Canop=PlantsPhysChar['Canops']
    hCanop=Canop['CanopHeight'];
    NCanop=Canop['CanopDens']
    dCanop=Canop['CanopDiam']
    CdC=Canop['CanopCd']
    
    # create relative depth values for roots, trunk and canopy
    alphr=hRoots/ho;alpht=hTrunk/ho;alphc=hCanop/ho
    for kk in range(lx): 
        if alphr[kk]>1:
            alphr[kk]=1;alpht[kk]=0.000000001;alphc[kk]=0.00000001 # roots only
        elif alphr[kk]+alpht[kk]>1:
            alpht[kk]=1-alphr[kk];alphc[kk]=0.000000001 # roots and trunk
        elif alphr[kk]+alpht[kk]+alphc[kk]>1:
            alphc[kk]=1-alphr[kk]-alpht[kk] # roots, trunk and canopy
    
    #Read Oyster reef Characteristics
    if Sr[Sr==3].any(): #Oyster reef
        oyster=PlantsPhysChar['Oyster']
        ReefLoc=ArtReefP[0]
        hc=ArtReefP[1]
        Bw=ArtReefP[2]
        Cw=ArtReefP[3]
        ReefType=ArtReefP[4]
        hi=mean(h[ReefLoc])
        case='main'
    
    #----------------------------------------------------------------------------------------
    #Initialize the model
    #----------------------------------------------------------------------------------------
    
    # Constants 
    H=lx*[0.];Db=lx*[0.];Df=lx*[0.];Diss=lx*[0.];H2=lx*[0.];Dveg=lx*[0.];
    C=lx*[0.];n=lx*[0.];Cg=lx*[0.];k=lx*[0.];L=lx*[0.];T=lx*[0.];Hmx=lx*[0.]
    Er=lx*[0.];Br=lx*[0.]
    
    #Forcing
    Ho=float(Ho);To=float(To);Uo=float(Uo);Surge=float(Surge);Etao=0.0
    sig=2*num.pi/To;fp=1*1.0/To; # Wave period, frequency etc.
    ki,C[0],Cg[0]=Fast_k(To,h[0]) #Wave number, length, etc
    Li=2*num.pi/ki;Lo=g*To**2*1.0/(2*num.pi);
    Kk=[];dd=gradient2(h,x);
    
    #Wave param
    Co=g*To/(2*num.pi);Cgo=Co/2;#Deep water phase speed
    k[0]=ki;
    H[0]=Ho
    T[0]=To;
    
    #Rms wave height
    temp1=2.0*pi/ki
    Hmx[0]=0.1*temp1*tanh(h[0]*ki);#Max wave height - Miche criterion
    if H[0]>Hmx[0]:
        H[0]=Hmx[0];
    
    #Wave and roller energy
    Db[0]=0.00001;Df[0]=0.00001;Diss[0]=0.00001; #Dissipation due to brkg,bottom friction and vegetation
    Dveg[0]=0.00001;Er[0]=0.00001;Br[0]=0.00001;
    
    #Whafis terms
    CorrFact=0.8; #Correction for estimating num.tanh as exp.
    Sin12=lx*[0.];t=lx*[0.];T=lx*[0.];Sin=lx*[0.];Inet=lx*[0.];Term=lx*[0.];L=lx*[0.]
    T2=lx*[0.];T3=lx*[0.];T4=lx*[0.];T5=lx*[0.];T6=lx*[0.];
    H2[0]=H[0]**2;d1=h[0];
    T[0]=To;t[0]=T[0]**3;
    
    at=7.54;gt=0.833;mt=1.0/3.0;sigt=0.0379;#Coeff. for wind wave period
    ah=0.283;gh=0.530;mh=0.5;sigh=0.00565;#Coeff. for wind wave height
    bt1=num.tanh(gt*(g*d1*1.0/Ua[0]**2.0)**0.375);
    bh1=num.tanh(gh*(g*d1*1.0/Ua[0]**2.0)**0.75);
    nut1=(bh1*1.0/sigh)**2.0*(sigt/bt1)**3.0;
    H_inf1=ah*bh1*Ua[0]**2*1.0/g;t_inf1=(at*bt1*Ua[0]/g)**3;
    
    D=d1*1.0/Lo;lam=2*k[0]*d1;
    T2[0]=num.sqrt(Lo*D/(num.sinh(2*num.pi*D)*num.cosh(2*num.pi*D)**3));
    T3[0]=num.tanh(2*num.pi*D)**.5*(1-2*num.pi*D/num.sinh(4*num.pi*D));
    T4[0]=2*num.pi*(1-lam*1*1.0/num.tanh(lam))/num.sinh(lam);
    T5[0]=num.pi/2*(1+lam**2*1*1.0/num.tanh(lam)/num.sinh(lam))*T2[0];
    T6[0]=g/(6*num.pi*T[0])*(1+lam**2*1*1.0/num.tanh(lam)/num.sinh(lam))*T3[0];
    if H[0]<=H_inf1 and t[0]<=t_inf1:
        Sin[0]=CorrFact*(at*sigt)**3.0/g*(Ua[0]/g)**factor*(1-(H[0]/H_inf1)**2.0)**nut1
    else:
        Sin[0]=0.00001
    
    if H_inf1<>0:
        Inet[0]=Cg[0]*T[0]*CorrFact*(sigh*ah*Ua[0])**2*1.0/g*(1-(H[0]/H_inf1)**2)+H[0]**2*T6[0]*Sin[0];
    else:
        Inet[0]=0.00001;
    if h[0]>10:
        Inet[0]=0.00001
    
    Term[0]=(T4[0]+T5[0]/num.sqrt(d1))*dd[0]+T6[0]*Sin[0];# Constants 
    kd=lx*[0.]
    ping1=0;ping2=0;ping3=0;
    
    #----------------------------------------------------------------------------------------
    # Begin wave model 
    #----------------------------------------------------------------------------------------
    for xx in range(lx-1) :#Transform waves, take MWL into account
        if h[xx]>.05: #make sure we don't compute waves in water deep enough
            
            #Determine wave period
            Uxx=Ua[xx] #wind speed
            Uxx1=Ua[xx+1]
            kd[xx]=k[xx]*h[xx]
            if h[xx]>10:
                Uxx=0.00001
                Uxx1=0.00001
        
            d1=h[xx+1];d2=h[xx];
            bt1=num.tanh(gt*(g*d1*1.0/Uxx1**2)**0.375);
            bh1=num.tanh(gh*(g*d1*1.0/Uxx1**2)**0.75);
            nut1=(bh1*1.0/sigh)**2*(sigt/bt1)**3;
            H_inf1=ah*bh1*Uxx1**2*1.0/g;t_inf1=(at*bt1*Uxx1*1.0/g)**3;
            bt2=num.tanh(gt*(g*d2*1.0/Uxx**2)**0.375);
            bh2=num.tanh(gh*(g*d2*1.0/Uxx**2)**0.75);
            nut2=(bh2*1.0/sigh)**2*(sigt/bt2)**3;
            H_inf2=ah*bh2*Uxx**2*1.0/g;t_inf2=(at*bt2*Uxx/g)**3;
        
            #Averages
            H_inf12=mean([H_inf1,H_inf2]);
            nut_12=mean([nut1,nut2]);
            t_inf12=mean([t_inf1,t_inf2]);
        
            #Solve for Period T
            if H[xx]<=H_inf12 and t[xx]<=t_inf12:
                Sin12[xx+1]=CorrFact*(at*sigt)**3*1.0/g*(Uxx1*1.0/g)**factor*(1-(H[xx]/H_inf12)**2)**nut_12;
            else:
                Sin12[xx+1]=0.00001;
        
            t[xx+1]=t[xx]+dx[xx]*Sin12[xx+1];
            #T[xx+1]=t[xx+1]**.3333;
            T[xx+1]=To;
            fp=1*1.0/T[xx+1];   
            k[xx+1],C[xx+1],Cg[xx+1]=Fast_k(To,h[xx+1])
        
            D=d1*1.0/Lo;lam=2*k[xx+1]*d1;
            T2[xx+1]=num.sqrt(Lo*D/(num.sinh(2*num.pi*D)*num.cosh(2*num.pi*D)**3));
            T3[xx+1]=num.tanh(2*num.pi*D)**.5*(1-2*num.pi*D/num.sinh(4*num.pi*D));
            T4[xx+1]=2*num.pi*(1-lam*1*1.0/num.tanh(lam))/num.sinh(lam);
            T5[xx+1]=num.pi/2*(1+lam**2*1*1.0/num.tanh(lam)/num.sinh(lam))*T2[xx+1];
            T6[xx+1]=g/(6.0*num.pi*T[xx+1])*(1+lam**2*1.0/num.tanh(lam)/num.sinh(lam))*T3[xx+1];
        
            if H[xx]<=H_inf1 and t[xx+1]<=t_inf1:
                Inet[xx+1]=(Cg[xx+1]*T[xx+1])*CorrFact*(sigh*ah*Uxx1)**2*1.0/g*(1-(H[xx]/H_inf1)**2)+H[xx]**2*T6[xx+1]*Sin12[xx+1];
            else:
                Inet[xx+1]=0.00001;
        
            Term[xx+1]=(T4[xx+1]+T5[xx+1]/num.sqrt(d1))*dd[xx+1]+T6[xx+1]*Sin12[xx+1];# Constants 
        
            #Other Diss. Terms    
         
            Gam=0.78;B=1;
            Db[xx]=(3.0/16)*num.sqrt(num.pi)*rho*g*(B**3)*fp*((H[xx]/num.sqrt(2))**7)/ ((Gam**4)*(h[xx]**5)); #Dissipation due to brkg    
            Df[xx]=1.0*rho*Cf[xx]/(16.0*num.sqrt(num.pi))*(2*num.pi*fp*(H[xx]/num.sqrt(2.0))/num.sinh(k[xx]*h[xx]))**3;#Diss due to bot friction 
        
            # dissipation due to vegetation
            V1=3.0*num.sinh(k[xx]*alphr[xx]*h[xx])+num.sinh(k[xx]*alphr[xx]*h[xx])**3.0 # roots
            V2=(3.0*num.sinh(k[xx]*(alphr[xx]+alpht[xx])*h[xx])-3.0*num.sinh(k[xx]*alphr[xx]*h[xx])+
                num.sinh(k[xx]*(alphr[xx]+alpht[xx])*h[xx])**3.0-
                num.sinh(k[xx]*alphr[xx]*h[xx])**3) # trunk
            V3=(3.0*num.sinh(k[xx]*(alphr[xx]+alpht[xx]+alphc[xx])*h[xx])
                -3.0*num.sinh(k[xx]*(alphr[xx]+alpht[xx])*h[xx])+
                num.sinh(k[xx]*(alphr[xx]+alpht[xx]+alphc[xx])*h[xx])**3.0-
                num.sinh(k[xx]*(alphr[xx]+alpht[xx])*h[xx])**3.0) # canopy
        
            CdDN=CdR[xx]*dRoots[xx]*NRoots[xx]*V1+CdT[xx]*dTrunk[xx]*NTrunk[xx]*V2+CdC[xx]*dCanop[xx]*NCanop[xx]*V3
            temp1=rho*CdDN*(k[xx]*g/(2.0*sig))**3.0/(2.0*num.sqrt(num.pi))
            temp3=(3.0*k[xx]*num.cosh(k[xx]*h[xx])**3)
            Dveg[xx]=temp1*1.0/temp3*(H[xx]/num.sqrt(2.0))**3 # dissipation due to vegetation
        
            Fact=16.0/(rho*g)*T[xx+1];
            Diss[xx+1]=Fact*(Db[xx]+Df[xx]+Dveg[xx]);
        
            Inet12=mean([Inet[xx],Inet[xx+1]]);
            
            Term12=mean([Term[xx],Term[xx+1]]);
            if Uo==0: 
                #Term12=0.00001;
                Inet12=0.00001;
                
            H2[xx+1]=H2[xx]+dx[xx]/(Cg[xx]*T[xx])*(Inet12-Diss[xx]-H2[xx]*Term12);
            if H2[xx+1]<0:
                H2[xx+1]=1e-4;
            H[xx+1]=num.sqrt(H2[xx+1]);
            #Hmx[xx+1]=0.1*(2.0*pi/k[xx+1])*tanh(h[xx+1]*k[xx+1]);#Max wave height - Miche criterion
            #if H[xx+1]>Hmx[xx+1]:
                #H[xx+1]=Hmx[xx+1]
    
            if Sr[xx+1]==3:
                if xx+1 in ReefLoc:
                    Rloc=ReefLoc[0]-1
                    Kt,wavepass,msgO,msgOf,ping1,ping2,ping3=BreakwaterKt(H[Rloc],To,hi,hc,Cw,Bw,case,ping1,ping2,ping3)
                    Kk.append(float(Kt))
                    H[xx+1]=Kt*H[Rloc]
                    H2[xx+1]=H[xx+1]**2.0
            
            Br[xx+1]=Br[xx]-dx[xx]*(g*Er[xx]*sin(Beta)/C[xx]-0.5*Db[xx]) # roller flux
            Er[xx+1]=Br[xx+1]/(C[xx+1]) # roller energy
        
        
        #Art. reef transmission coefficient
        if len(Kk)>0:
            Kk=array(Kk)
            Kt=mean(Kk)
            if Kt>0.98:
                Kt=1.0
        else:
            Kt=1.0;
            
        #Interpolate profile of wave height over oyster reef
        if Sr[xx+1]==3 and Kt<0.95:
            Hrf=array(H)
            Hrf[-1]=Hrf[-2];
            temp1=array(x);temp2=temp1.tolist()
            temp1= [ item for i,item in enumerate(temp1) if i not in ReefLoc ]
            Hrf=[item for i,item in enumerate(Hrf) if i not in ReefLoc ]
            F=interp1d(temp1,Hrf);
            Hrf=F(temp2)
            H=array(Hrf)
        
    H=smooth(num.array(H),len(H)*0.01,'hanning')             
    Ew=lx*[0.0];Ew=[0.125*rho*g*(H[i]**2.0) for i in range(lx)] # energy density
    ash=array(h)
    
    #-------------------------------------------------------------------------------------------------
    #Mean Water Level
    #-------------------------------------------------------------------------------------------------
    # force on plants if they were emergent; take a portion if plants occupy only portion of wc
    Fxgr=[rho*g*CdR[i]*dRoots[i]*NRoots[i]*H[i]**3.0*k[i]/(12.0*num.pi*num.tanh(k[i]*ash[i])) for i in range(lx)]
    Fxgt=[rho*g*CdT[i]*dTrunk[i]*NTrunk[i]*H[i]**3.0*k[i]/(12.0*num.pi*num.tanh(k[i]*ash[i])) for i in range(lx)]
    Fxgc=[rho*g*CdC[i]*dCanop[i]*NCanop[i]*H[i]**3.0*k[i]/(12.0*num.pi*num.tanh(k[i]*ash[i])) for i in range(lx)]
    fx=[-alphr[i]*Fxgr[i]-alpht[i]*Fxgt[i]-alphc[i]*Fxgc[i] for i in range(lx)] # scale by height of indiv. elements
    fx=smooth(num.array(fx),len(fx)*0.01,'hanning')     
    
    # estimate MWS without the vegetation
    X=x;
    dx = 1   






    Sxx=lx*[0.0];Rxx=lx*[0.0];Eta_nv=lx*[0.0];O=0;
    while O<8: # iterate until convergence of water level
        hi=[ash[i]+Eta_nv[i] for i in range(lx)] # water depth        
        
        Sxx=[0.5*Ew[i]*(4.0*k[i]*h[i]/num.sinh(2.0*k[i]*h[i])+1.0) for i in range(lx)] # wave radiation stress
        

        Rxx=[2.0*Er[i] for i in range(lx)] # roller radiation stress
        # estimate MWL along Xshore transect
        temp1=[Sxx[i]+Rxx[i] for i in range(lx)]
        
#        print('temp1', num.array(temp1).shape)
#        print('dx', dx.shape)
#        sys.exit(0)

        temp2=num.gradient(num.array(temp1),dx)
    
        Integr=[(-temp2[i])/(rho*g*h[i]) for i in range(lx)]
        Eta_nv[0]=Etao
        Eta_nv[1]=Eta_nv[0]+Integr[0]*dx
        for i in range(1,lx-2):
            Eta_nv[i+1]=Eta_nv[i-1]+Integr[i]*2*dx
        Eta_nv[lx-1]=Eta_nv[lx-2]+Integr[lx-1]*dx
        O=O+1
        
    
    #Rerun with vegetation
    temp=next((i for i, x in enumerate(Dveg) if x), None) #Check if there's vegetation
    
    if temp is not None: #There's vegetation. Compute MWL
        Sxx=lx*[0.0];Rxx=lx*[0.0];Eta=lx*[0.0];O=0;
        while O<8: # iterate until convergence of water level
            hi=[ash[i]+Eta[i] for i in range(lxi)] # water depth        
            Sxx=[0.5*Ew[i]*(4.0*k[i]*h[i]/num.sinh(2.0*k[i]*h[i])+1.0) for i in range(lxi)] # wave radiation stress
            Rxx=[2.0*Er[i] for i in range(lx)] # roller radiation stress
            # estimate MWL along Xshore transect
            temp1=[Sxx[i]+Rxx[i] for i in range(lxi)]
            temp2=num.gradient(num.array(temp1),dx)
        
            Integr=[(-temp2[i]+fx[i])/(rho*g*h[i]) for i in range(lx)]
            Eta[0]=Etao
            Eta[1]=Eta[0]+Integr[0]*dx
            for i in range(1,lx-2):
                Eta[i+1]=Eta[i-1]+Integr[i]*2*dx
            Eta[lx-1]=Eta[lx-2]+Integr[lx-1]*dx
            O=O+1
    else:
        Eta=[Eta_nv[ii] for ii in range(lx)]            
    
    Ubot=[num.pi*H[ii]/(To*num.sinh(k[ii]*h[ii])) for ii in range(lx)] # bottom velocity
    Ur=[(Ew[ii]+2.0*Er[ii])/(1024.0*h[ii]*C[ii])for ii in range(lx)] 
    Ic=[Ew[ii]*Cg[ii]*Ur[ii]/Ubot[ii] for ii in range(lx)]
    
    H_=num.zeros(lxo)+nan;Eta_=num.zeros(lxo)+nan
    Eta_nv_=num.zeros(lxo)+nan
    Ur_=num.zeros(lxo)+nan;Ic_=num.zeros(lxo)+nan
    Ubot_=num.zeros(lxo)+nan;Kt_=num.zeros(lxo)+nan
    H_[0:lx]=H;Eta_[0:lx]=Eta;Eta_nv_[0:lx]=Eta_nv;
    Ur_[0:lx]=Ur;Ic_[0:lx]=Ic
    Ubot_[0:lx]=Ubot;Kt_[0:lx]=Kt
    other=[0.1*(2.0*pi/k[ii])*tanh((h[ii])*k[ii]) for ii in range(len(k))]
    
    return H_,Eta_,Eta_nv_,Ubot_,Ur_,Kt_,Ic_,Hmx,other # returns: wave height, wave setup, wave height w/o veg., wave setup w/o veg, wave dissipation, bottom wave orbital velocity over the cross-shore domain
        #End of WaveRegen

def BreakwaterKt(Hi,To,hi,hc,Cwidth,Bwidth,case,ping1,ping2,ping3):
    hi=round(hi,2);hc=round(hc,2);hco=hc;
    Lo=9.81*To**2.0/(2.0*num.pi)
    Rc=hc-hi # depth of submergence
    difht=abs(hc-hi);difht=str(difht)

    if Cwidth<>0:
        ReefType='Trapez'
    else:
        ReefType='Dome'
        
    if Rc>0 and ReefType=="Dome":
        print("The artificial structure is emerged by "+difht+" m. It blocks all incoming waves.We make it smaller so it reaches the water surface")
        hc=hi-.01
        Rc=hc-hi

    
    msgO="";msgOf=""
    wavepass=abs(0.095*Lo*num.tanh(2.0*num.pi*Rc/Lo))
    if Hi<wavepass and hi>hc:
        Kt=1;
        wavepass=1#wave doesn't break
        if case=='main' and ping1==0:
            print("Under current wave conditions, the reef is small enough that it doesn't break the waves. Energy is dissipated via bottom friction.  You can try to increase your reef height to see a larger effect on waves.") #BREAK
            msgO=msgO+"Under current wave conditions, the reef is small enough that it doesn't break the waves. Energy is dissipated via bottom friction.  You can try to increase your reef height to see a larger effect on waves."
            ping1=1
    
    elif ReefType=="Trapez": # it's not a reef ball
        wavepass=0 #wave breaks
        if hc/hi<0.5: #The reef is too submerged
            hc=round(0.5*hi,2);hcf=round(3.28*hc,2);hcof=round(3.28*hco,2);
            if case=='main' and ping3==0:
                    msgO=msgO+"Under current wave conditions, the reef affects waves, but its size is outside the validity range of our simple model. We increase it by "+str(hc-hco)+" m to continue our computation."
                    msgOf=msgOf+"Under current wave conditions, the reef affects waves, but its size is outside the validity range of our simple model. We increase it by "+str(round(3.28*(hc-hco),2))+" ft to continue our computation."
                    ping3=1
        if abs(Rc/Hi)>6:
            hc=round(6*Hi+hi,2)
            if case=='main' and ping2==0:
                    msgO=msgO+"Under current wave conditions, the reef height is above the range of validity of our simple model. We change it to "+str(hc)+" m from "+str(hco)+" m to continue our computation."
                    msgOf=msgOf+"Under current wave conditions, the reef height is above the range of validity of our simple model. We change it to "+str(hcf)+" ft from "+str(hcof)+" ft to continue our computation."
                    ping2=1
            
        Rc=hc-hi # depth of submergence
        Boff=(Bwidth-Cwidth)/2.0 # base dif on each side
        ksi=(hc/Boff)/num.sqrt(Hi/Lo)
        
        # van der Meer (2005)
        Kt1=-0.4*Rc/Hi+0.64*(Cwidth/Hi)**(-.31)*(1.0-num.exp(-0.5*ksi)) # transmission coeff: d'Angremond
        Kt1=max(Kt1,0.075);Kt1=min(0.8,Kt1);
    
        Kt2=-0.35*Rc/Hi+0.51*(Cwidth/Hi)**(-.65)*(1.0-num.exp(-0.41*ksi)) # transmission coeff: van der Meer
        Kt2=max(Kt2,0.05);Kt2=min(Kt2,-0.006*Cwidth/Hi+0.93)
    
        if Cwidth/Hi<8.0: # d'Angremond
            Kt=Kt1
        elif Cwidth/Hi>12.0: # van der Meer
            Kt=Kt2
        else: # linear interp
            temp1=(Kt2-Kt1)/4.0;temp2=Kt2-temp1*12.0
            Kt=temp1*Cwidth/Hi+temp2
            
    else: # it's a reef ball
        Rc=hi-hc
        wavepass=0 #wave breaks
        Kto=1.616-31.322*Hi/(9.81*To**2)-1.099*hc/hi+0.265*hc/Bwidth #D'Armono and Hall

        #New Formula
        Bt=0.6*Bwidth
        KtLow=(-.2496*min(4.0,Bt/sqrt(Hi*Lo))+.9474)**2.0
        KtHigh=1.0/(1+.3*(Hi/Rc)**1.5*Bt/sqrt(Hi*Lo))
        if Rc/Hi<=0.4:
            Kt=KtLow
        elif Rc/Hi>=.71:
            Kt=KtHigh
        else:
            a=(KtLow-KtHigh)/(0.4-0.71)
            b=KtLow-a*0.4
            Kt=a*Rc/Hi+b
        if Kt>1:
            Kt=1
        Kt=min(Kt,Kto)
        print(str(Kt))
        
        if hc>hi:
            Kt=1
            difht=abs(hc-hi);difht=str(difht)
            if case=='main':
                msgO=msgO+"The reef balls are emerged by "+difht+" m. They completely block all incoming waves."
        elif Kt>1:
            Kt=1
            if case=='main':
                msgO=msgO+"Your layout is outside of the range of validity of our simple equation, but it is likely that it doesn't have an effect on waves."
          
    if Kt<0:
        Kt=1  #No transmission - breakwater fully emerged
        if case=='main':
            msgO=msgO+"Your reef is fully emerged and blocks the incoming wave."
    return Kt,wavepass,msgO,msgOf,ping1,ping2,ping3
#End of BreakwaterKt



