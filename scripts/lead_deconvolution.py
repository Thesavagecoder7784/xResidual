#!/usr/bin/env python3
"""Recover the distribution of TRUE cross-venue leads from the published, bias-contaminated ones.

The lead-lag estimator is biased because Kalshi's mid is seen at 1 Hz while Polymarket's is seen at
~10 ms (see sampling_bias_check.py). The bias is not a constant, so it cannot simply be subtracted.
But the estimator's RESPONSE to a known true lead is measurable: shift a real Polymarket path by a
known lag L, observe it at 1 Hz, and histogram what the estimator reports. Doing that over a grid of
L gives a response matrix R. The published histogram y is then y ~= R w, and w -- the distribution of
true leads -- follows by non-negative least squares.

This needs no raw tapes: it runs on the committed per-event leads in _leadlag_results.json plus the
per-tick windows in viz/market/leadlag (withheld). A self-test inverts samples drawn from known
truths first, so the recovered numbers come with a demonstrated recovery rate.

    python scripts/lead_deconvolution.py
"""
import json, glob, bisect, random, sys, os
import numpy as np
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import ws_events as we
from scipy.optimize import nnls
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S=os.path.join(ROOT,"writeups")
random.seed(5)
LAGS=[-3000,-2000,-1500,-1000,-600,-300,0,300,600,1000,1500,2000,3000]
PHASES=60
EDGES=np.array([-8000,-3000,-2000,-1200,-600,-200,1,200,600,1000,1200,2000,3000,8001])
wins=[]
for f in sorted(glob.glob(os.path.join(ROOT,"viz","market","leadlag","*.js"))):
    s=open(f).read(); s=s[s.index("{"):].rstrip().rstrip(";")
    try: w=json.loads(s)
    except ValueError: continue
    p=[(int(round(t*1000)),v) for t,v in w["data"]["poly"]]; k=[(int(round(t*1000)),v) for t,v in w["data"]["kalshi"]]
    if len(p)>50 and len(k)>10: wins.append((p,k))
def hold(src,stamps):
    ts=[x[0] for x in src]; out=[]
    for t in stamps:
        i=bisect.bisect_right(ts,t)-1
        if i>=0: out.append((t,src[i][1]))
    return out
def gated(k,p):
    ll=we.lead_lag_ms(k,p,bin_ms=200,max_lag_ms=20000)
    if not ll or ll["best_corr"]<0.5 or abs(ll["best_lag_ms"])>8000: return None
    return ll["best_lag_ms"]
raw={}
for L in LAGS:
    got=[]
    for p,k in wins:
        sh=[(t+L,v) for t,v in p]
        for _ in range(PHASES):
            ph=random.randrange(1000); lo,hi=p[0][0],p[-1][0]
            r=gated(hold(sh,list(range(lo-(lo%1000)+ph,hi,1000))),p)
            if r is not None: got.append(r)
    raw[L]=got
    print("built L=",L,len(got),flush=True)
R=np.zeros((len(EDGES)-1,len(LAGS)))
for j,L in enumerate(LAGS):
    h,_=np.histogram(raw[L],bins=EDGES); R[:,j]=h/max(1,len(raw[L]))

def invert(sample):
    y,_=np.histogram(sample,bins=EDGES); y=y/max(1,len(sample))
    w,_=nnls(R,y); return w/w.sum() if w.sum()>0 else w
def masses(w): return (sum(x for L,x in zip(LAGS,w) if L<0), sum(x for L,x in zip(LAGS,w) if L==0), sum(x for L,x in zip(LAGS,w) if L>0))
SELFTEST=[]
print("\nSELF-TEST (draw 427 measurements from a KNOWN truth, then invert):")
rng=np.random.default_rng(1)
for name,truth in [("all +600 (Poly leads)",{600:1.0}),("all 0 (no lead)",{0:1.0}),("all -600 (Kalshi leads)",{-600:1.0}),
                   ("half 0 / half +600",{0:.5,600:.5}),("60% 0, 20% -600, 20% +600",{0:.6,-600:.2,600:.2})]:
    samp=[]
    for L,frac in truth.items():
        pool=raw[L]; samp+=list(rng.choice(pool,size=int(round(427*frac)),replace=True))
    w=invert(samp); k,z,p=masses(w)
    tk=sum(f for L,f in truth.items() if L<0); tz=sum(f for L,f in truth.items() if L==0); tp=sum(f for L,f in truth.items() if L>0)
    print(f"  truth K/0/P = {tk:.0%}/{tz:.0%}/{tp:.0%}   recovered = {k:.0%}/{z:.0%}/{p:.0%}")
    SELFTEST.append({"truth":name,"truth_masses":[tk,tz,tp],"recovered":[k,z,p]})
pub=[]
def walk(o):
    if isinstance(o,dict):
        if isinstance(o.get("best_lag_ms"),(int,float)): pub.append(o["best_lag_ms"])
        for v in o.values(): walk(v)
    elif isinstance(o,list):
        for v in o: walk(v)
walk(json.load(open(os.path.join(ROOT,"writeups","_leadlag_results.json"))))
w=invert(pub); k,z,p=masses(w)
print(f"\nPUBLISHED {len(pub)} events -> true-lead masses  Kalshi-first {k:.1%} | none {z:.1%} | Poly-first {p:.1%}")
bs=[]
for _ in range(400):
    b=rng.choice(pub,size=len(pub),replace=True); bs.append(masses(invert(b)))
bs=np.array(bs)
for i,lab in enumerate(["Kalshi-first","none","Poly-first"]):
    print(f"   {lab:<13} 95% [{np.percentile(bs[:,i],2.5):.1%}, {np.percentile(bs[:,i],97.5):.1%}]")
json.dump({"lags":LAGS,"weights":w.tolist(),"masses":{"kalshi":k,"none":z,"poly":p},
           "bootstrap95":{lab:[float(np.percentile(bs[:,i],2.5)),float(np.percentile(bs[:,i],97.5))] for i,lab in enumerate(["kalshi","none","poly"])},
           "n_published":len(pub),"self_test":SELFTEST,"response_grid_ms":LAGS,"phases_per_window":PHASES}, open(os.path.join(S,"_lead_deconvolution_results.json"),"w"), indent=1)
print("DONE")
