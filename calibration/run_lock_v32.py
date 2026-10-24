"""UCSRS v3.2 registry-anchored calibration run (24 October 2026).

Usage: python3 run_lock_v32.py TOTAL SEED_OFFSET TAG [SHIFTS]
  locking run : python3 run_lock_v32.py 30000000 0 lock30M
  hold-outs   : python3 run_lock_v32.py 2600000 500000 hold1 0.581 ; ... 900000 hold2 0.581
Scores every simulated patient at each shift in the list and reports median O/E per shift. No outcome is simulated.
Results are written to results/TAG.json. Uses the same cohort generator and registry dials as the v3.1 runs.
"""
import sys, json, time, numpy as np
import os
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,os.path.join(HERE,"..")); sys.path.insert(0,HERE)
import ucsrs_engine as E
from cohort import Cohort, rows
from anchors import REGISTRIES
from multiprocessing import Pool
dials={d["name"]:(d["dial"],d["seed"]) for d in json.load(open(os.path.join(HERE,"results","registry_dials.json")))}
names=[r[0] for r in REGISTRIES]; obs={r[0]:r[5] for r in REGISTRIES}
SHIFTS=[0.50,0.52,0.54,0.56,0.581,0.60,0.62,0.64,0.66]
def prep(r):
    p=E.patient_from_row(r)
    cog_raw=E._text(r.get("cog_impaired")); cog=None if cog_raw=="" else cog_raw not in ("0","no","n","false")
    eft=E.eft_score(E.p_chair(r),cog,E._num(r.get("hgb_g_dl")),E._num(r.get("albumin_g_dl")),p["female"])["points"]
    meld=None; b,i=E._num(r.get("bilirubin_mg_dl")),E._num(r.get("inr"))
    if b is not None and i is not None: meld=E.meld_from_labs(b,i,p["creatinine"])
    kw=dict(lvesvi=E._num(r.get("lvesvi_ml_m2")),lvedd=E._num(r.get("lvedd_mm")),syntax=E._num(r.get("syntax_score")),tier=2 if E._num(r.get("rhc_map_mmhg")) is not None else 0,map_mmhg=E._num(r.get("rhc_map_mmhg")),co=E._num(r.get("rhc_co_l_min")),pvr=E._num(r.get("rhc_pvr_wu")))
    return p,eft,meld,kw
def block(job):
    nm,seed,dial,n,shifts=job
    S=len(shifts); sm=np.zeros(S); cap=np.zeros(S); gt30=np.zeros(S)
    for r in rows(Cohort(seed).draw(n,dial)):
        p,eft,meld,kw=prep(r)
        for k,sh in enumerate(shifts):
            E.BASELINE_A2["calibration_shift"]=sh
            f=E.ucsrs(E.physiology_baseline(p),eft,meld,**kw)["final"]
            sm[k]+=f; cap[k]+= f>=69.999; gt30[k]+= f>30
    return nm,n,sm,cap,gt30
def run(total,seedoff,shifts,tag,chunk=50000):
    per=total//len(names); jobs=[]
    for nm in names:
        d,s=dials[nm]; left=per; i=0
        while left>0:
            c=min(chunk,left); jobs.append((nm,s+seedoff+1000*i,d,c,shifts)); left-=c; i+=1
    acc={nm:[0,np.zeros(len(shifts)),np.zeros(len(shifts)),np.zeros(len(shifts))] for nm in names}
    t=time.time()
    with Pool(2) as pool:
        for j,(nm,n,sm,cap,g) in enumerate(pool.imap_unordered(block,jobs)):
            a=acc[nm]; a[0]+=n; a[1]+=sm; a[2]+=cap; a[3]+=g
            if j%20==0: print(tag,f"{j}/{len(jobs)} {time.time()-t:.0f}s",flush=True)
    out={}
    for k,sh in enumerate(shifts):
        oe=[obs[nm]/(acc[nm][1][k]/acc[nm][0]) for nm in names]
        n=sum(acc[nm][0] for nm in names)
        out[sh]=dict(medOE=float(np.median(oe)),mae_log=float(np.mean(np.abs(np.log(oe)))),inband=int(sum(0.8<=o<=1.2 for o in oe)),
            pct_cap=100*sum(acc[nm][2][k] for nm in names)/n,pct_gt30=100*sum(acc[nm][3][k] for nm in names)/n,oe=dict(zip(names,map(float,oe))),n=n)
    json.dump(out,open(os.path.join(HERE,"results",f"{tag}.json"),"w"),indent=1); return out
if __name__=="__main__":
    tot=int(sys.argv[1]); off=int(sys.argv[2]); tag=sys.argv[3]
    sh=SHIFTS if len(sys.argv)<5 else [float(x) for x in sys.argv[4].split(",")]
    o=run(tot,off,sh,tag)
    for k,v in o.items(): print(k,{a:b for a,b in v.items() if a!="oe"})
