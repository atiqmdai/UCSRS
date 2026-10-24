"""UCSRS v3.2 high-risk validation, 1,000,000 patients (24 October 2026). Same profile and seed as v3.1 (run_highrisk_1M.py).
EuroSCORE II is computed by a standalone implementation of the published formula (the engine no longer computes it).
No outcome is simulated."""
import sys,json,math,time,numpy as np
from multiprocessing import Pool
import os
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,os.path.join(HERE,".."))
import ucsrs_engine as E
def es2(r,p):
    age=p["age"]; x=-5.324537+0.0285181*max(1,age-59)
    if p["female"]: x+=0.2196434
    if p["dialysis"]: x+=0.6421508
    else:
        cc=(140-age)*p["weight"]/(72*p["creatinine"])*(0.85 if p["female"] else 1)
        x+= 0.8592256 if cc<50 else (0.303553 if cc<=85 else 0)
    if E._text(r.get("arteriopathy_site")) in ("carotid","peripheral"): x+=0.5360268
    if r.get("poor_mobility"): x+=0.2407181
    if p["prevCardiac"]: x+=1.118599
    if p["pulmStatus"] in ("chronic","chronic_o2"): x+=0.1886564
    if p["endocarditis"]: x+=0.6194522
    if p["critical"]: x+=1.086517
    if p["iddm"]: x+=0.3542749
    x+={1:0,2:0.1070545,3:0.2958358,4:0.5597929}[p["nyha"]]
    if p["ccs4"]: x+=0.2226147
    ef=p["lvef"]
    x+= 0.9346919 if ef<=20 else 0.8084096 if ef<=30 else 0.3150652 if ef<=50 else 0
    if p["recentMI"]: x+=0.1528943
    ps=p["pasp"]
    if ps is not None: x+= 0.3491475 if ps>55 else 0.1788899 if ps>=31 else 0
    x+={"elective":0,"urgent":0.3174673,"emergency":0.7039121,"salvage":1.362947}[p["urgency"]]
    x+={"cabg":0,"single":0.0062118,"two":0.5521478,"three":0.9724533}[p["interventionWeight"]]
    if p["thoracicAorta"]: x+=0.6527205
    return 100/(1+math.exp(-x))

N=1_000_000; SEED=20260920
BASE=dict(height_cm=175,weight_kg=80,lvef_pct=55,pulm_status="none",renal_status="none",procedure_code="cabg_isolated",urgency="elective",operation_number="1",hgb_g_dl=9.0,albumin_g_dl=3.0,inr=2.0,bilirubin_mg_dl=2.5,chair_rise="slow",cog_impaired="1")
def mk(age,fem,cr,ef,hgb,alb,inr,bili,chair,cog):
    return dict(BASE,age_years=float(age),sex="F" if fem else "M",height_cm=170.0,weight_kg=78.0,creatinine_mg_dl=float(cr),lvef_pct=float(ef),hgb_g_dl=float(hgb),albumin_g_dl=float(alb),inr=float(inr),bilirubin_mg_dl=float(bili),chair_rise=str(chair),cog_impaired="1" if cog else "0")
def work(a):
    lo,hi,cols=a; out=np.empty((hi-lo,5))
    for k in range(hi-lo):
        i=lo+k; r=mk(*[c[i] for c in cols]); o=E.score_row(r); p=E.patient_from_row(r)
        out[k]=(o["ucsrs"],es2(r,p),o["meld"],o["eft"],o["baseline_pct"])
    return out
if __name__=="__main__":
    rng=np.random.default_rng(SEED)
    age=rng.choice([70,80],N)+rng.normal(0,3,N); fem=rng.random(N)<0.35
    cr=np.exp(rng.normal(np.log(2.6),0.35,N)).clip(1.2,6.0); alb=rng.normal(3.0,0.35,N).clip(1.8,4.2)
    inr=rng.normal(2.0,0.35,N).clip(1.0,4.5); bili=np.exp(rng.normal(np.log(2.5),0.5,N)).clip(0.4,20)
    hgb=rng.normal(9.0,1.1,N).clip(6.0,13.5); ef=rng.normal(55,5,N).clip(40,70)
    chair=rng.choice(["slow","unable"],N,p=[0.7,0.3]); cog=rng.random(N)<0.8
    cols=(age,fem,cr,ef,hgb,alb,inr,bili,chair,cog)
    # exact cells
    cells=[]
    for a in (70,80):
      for s in (False,True):
        for c in (2.0,4.0):
          r=mk(a,s,c,55,9.0,3.0,2.0,2.5,"slow",True); o=E.score_row(r); cells.append((a,"F" if s else "M",c,o["meld"],o["eft"],o["baseline_pct"],o["ucsrs"],es2(r,E.patient_from_row(r))))
    step=50000; t=time.time()
    with Pool(2) as P: res=np.concatenate(P.map(work,[(i,i+step,cols) for i in range(0,N,step)]))
    U,Ee,ML,FT,L1=res.T; cap=U>=69.99
    pc=lambda x,q: float(np.percentile(x,q))
    R=dict(spec=E.SPEC_VERSION,shift=E.BASELINE_A2["calibration_shift"],n=N,meld_mean=float(ML.mean()),meld_ge20=float((ML>=20).mean()*100),ft_mean=float(FT.mean()),ft_ge4=float((FT>=4).mean()*100),
      esii=dict(mean=float(Ee.mean()),p10=pc(Ee,10),p50=pc(Ee,50),p90=pc(Ee,90)),ucsrs=dict(mean=float(U.mean()),p10=pc(U,10),p50=pc(U,50),p90=pc(U,90)),layer1_mean=float(L1.mean()),
      ratio_of_means=float(U.mean()/Ee.mean()),median_ratio=float(np.median(U/Ee)),at_cap=float(cap.mean()*100),ge50=float((U>=50).mean()*100),ge30=float((U>=30).mean()*100),
      uncapped=dict(n=int((~cap).sum()),p10=pc(U[~cap],10),p50=pc(U[~cap],50),p90=pc(U[~cap],90)),cells=cells,secs=time.time()-t)
    json.dump(R,open(os.path.join(HERE,"results","highrisk_1M_v32.json"),"w"),indent=1); print(json.dumps(R,indent=1))
