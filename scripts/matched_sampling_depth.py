#!/usr/bin/env python3
"""Which section 6.2 claims survive once BOTH venues are sampled the same way?

Companion to sampling_bias_check.py. The published Kalshi top-of-book comes from the 1 Hz `ticker`
channel while Polymarket's comes from its full book (~10 ms), so any cross-venue comparison of depth
compares ~5 samples per event window against ~500. More samples means more chances to catch a
momentary trough. This mirrors build_harvest's definitions exactly (PRE/POST/REACT_WIN/SPREAD_WIN,
MIN_JUMP, the depth_frac ratio) and varies ONLY the sampling:

  poly_depth_frac_full_res   vs  poly_depth_frac_at_1hz        (Polymarket cut to Kalshi's cadence)
  kalshi_depth_frac_ticker   vs  kalshi_depth_frac_full_book   (Kalshi rebuilt from orderbook deltas)
  gross_cents_ticker         vs  gross_cents_full_book         (is the goal-sized move a stale-quote effect?)
  follower_kalshi_share      under each                        (who the ledger calls the follower)

Kalshi rebuilds are used only where they agree with Kalshi's own ticker quote 95%+ of the time.
Inputs are withheld raw tapes; the artifact is per-contract medians only. Small n - indicative.

    python scripts/matched_sampling_depth.py [--tapes ~/xResidual-vm-backup/logger-data]
"""
import argparse, json, os, sys, bisect, statistics as st
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0]=[ROOT, os.path.join(ROOT,"scripts")]
from xresidual import ws_events as we
import stream_micro as sm
from build_harvest import MIN_JUMP, PRE, POST, REACT_WIN, SPREAD_WIN, _win_med, _react_time, _spread_med, fee
from build_liquidity import detect_shocks
_ap=argparse.ArgumentParser(); _ap.add_argument("--tapes", default="~/xResidual-vm-backup/logger-data"); _a=_ap.parse_args()
D=os.path.expanduser(_a.tapes)
OUT=os.path.join(ROOT,"writeups","_matched_sampling_results.json")

def rebuild_tob(path, tickers):
    f=we._f; yes={t:{} for t in tickers}; no={t:{} for t in tickers}; have={t:False for t in tickers}; out={t:[] for t in tickers}
    def best(bk, hi):
        live=[(p,s) for p,s in bk.items() if s>0]
        return (max(live,key=lambda x:x[0]) if hi else min(live,key=lambda x:x[0])) if live else None
    for line in open(path,encoding="utf-8"):
        if '"kalshi"' not in line or 'orderbook_' not in line: continue
        try: e=json.loads(line)
        except ValueError: continue
        ty,m,d=e.get("type"),e.get("market"),e.get("data",{})
        if m not in tickers: continue
        if ty=="orderbook_snapshot":
            yes[m]={f(p):round(f(s),2) for p,s in d.get("yes_dollars_fp",[]) or []}
            no[m]={f(p):round(f(s),2) for p,s in d.get("no_dollars_fp",[]) or []}; have[m]=True
        elif ty=="orderbook_delta" and have[m]:
            p,dl=f(d.get("price_dollars")),f(d.get("delta_fp"))
            if p is None or dl is None: continue
            bk=yes[m] if d.get("side")=="yes" else no[m]; bk[p]=round(bk.get(p,0.0)+dl,2)  # 2-dp fixed point: no float residue on emptied levels
        else: continue
        b=best(yes[m],True); n=best(no[m],True)
        if not b or not n: continue
        bid,bsz=b; ask,asz=1-n[0],n[1]
        if ask<bid-1e-9: continue
        s=out[m]; row={"t":e["t"],"bid":bid,"ask":ask,"bid_sz":bsz,"ask_sz":asz}
        if not s or s[-1]["bid"]!=bid or s[-1]["ask"]!=ask or s[-1]["bid_sz"]!=bsz or s[-1]["ask_sz"]!=asz or e["t"]-s[-1]["t"]>1000:
            s.append(row)
    return out

def sub_tob(tob, stamps):
    ts=[r["t"] for r in tob]; out=[]
    for t in stamps:
        i=bisect.bisect_right(ts,t)-1
        if i>=0: out.append({**tob[i],"t":t})
    return out
def sub_mid(mid, stamps):
    ts=[x[0] for x in mid]; out=[]
    for t in stamps:
        i=bisect.bisect_right(ts,t)-1
        if i>=0: out.append((t,mid[i][1]))
    return out
dep=lambda r:(r["bid_sz"] or 0.0)+(r["ask_sz"] or 0.0)
def depth_frac(tob,t):
    dpre=[dep(r) for r in tob if t+PRE[0]<=r["t"]<=t+PRE[1]]
    dat=[dep(r) for r in tob if t+SPREAD_WIN[0]<=r["t"]<=t+SPREAD_WIN[1]]
    return (min(dat)/st.median(dpre)) if (dpre and dat and st.median(dpre)>0) else None

res={}
for cap in ["20260718T202817Z-france-vs-england","20260719T183322Z-spain-vs-argentina"]:
    path=os.path.join(D,f"ws-events-{cap}.jsonl"); pairs=we.load_pairs(D,cap)
    b=sm.stream_all(path,pairs); tickers={p["kalshi"] for p in pairs if p.get("kalshi")}
    kb=rebuild_tob(path,tickers)
    print(f"parsed {cap}",flush=True)
    for pr in pairs:
        kt,pa=pr.get("kalshi"),pr.get("poly")
        if not(kt and pa): continue
        km,pm=b["k_mid"][kt],b["p_mid"][pa]; ktob,ptob=b["k_tob"][kt],b["p_tob"][pa]; kbt=kb[kt]
        if len(km)<20 or len(pm)<20 or not kbt: continue
        stamps=[r["t"] for r in ktob]
        kbook_mid=[(r["t"],(r["bid"]+r["ask"])/2) for r in kbt]
        # trust check
        tb=[r[0] for r in kbook_mid]; ag=n=0
        for t,v in km:
            i=bisect.bisect_right(tb,t)-1
            if i>=0: n+=1; ag+=abs(kbook_mid[i][1]-v)<=0.005+1e-9
        trusted=(ag/n if n else 0)>=0.95
        rows={"poly_full":[], "poly_1hz":[], "k_ticker":[], "k_book":[], "gross_tick":[], "gross_book":[], "foll_tick":[], "foll_book":[]}
        for t in detect_shocks(pm):
            pre_k,pre_p=_win_med(km,t+PRE[0],t+PRE[1]),_win_med(pm,t+PRE[0],t+PRE[1])
            post_k,post_p=_win_med(km,t+POST[0],t+POST[1]),_win_med(pm,t+POST[0],t+POST[1])
            if None in (pre_k,pre_p,post_k,post_p): continue
            if abs((post_k+post_p)/2-(pre_k+pre_p)/2)<MIN_JUMP: continue
            rows["gross_tick"].append(abs((post_k+post_p)/2-(pre_k+pre_p)/2))
            rk=_react_time(km,pre_k,t+REACT_WIN[0],t+REACT_WIN[1]); rp=_react_time(pm,pre_p,t+REACT_WIN[0],t+REACT_WIN[1])
            if rk is not None and rp is not None: rows["foll_tick"].append("kalshi" if rp<=rk else "poly")
            pf,p1=depth_frac(ptob,t),depth_frac(sub_tob(ptob,stamps),t)
            if pf is not None: rows["poly_full"].append(pf)
            if p1 is not None: rows["poly_1hz"].append(p1)
            kf=depth_frac(ktob,t)
            if kf is not None: rows["k_ticker"].append(kf)
            if trusted:
                kbf=depth_frac(kbt,t)
                if kbf is not None: rows["k_book"].append(kbf)
                pre_kb=_win_med(kbook_mid,t+PRE[0],t+PRE[1]); post_kb=_win_med(kbook_mid,t+POST[0],t+POST[1])
                if None not in (pre_kb,post_kb):
                    rows["gross_book"].append(abs((post_kb+post_p)/2-(pre_kb+pre_p)/2))
                    rkb=_react_time(kbook_mid,pre_kb,t+REACT_WIN[0],t+REACT_WIN[1])
                    if rkb is not None and rp is not None: rows["foll_book"].append("kalshi" if rp<=rkb else "poly")
        m=lambda a: round(st.median(a),4) if a else None
        res[f"{cap[:8]}/{pr['label']}"]={"trusted_rebuild":trusted,"n_shocks":len(rows["gross_tick"]),
            "poly_depth_frac_full_res":m(rows["poly_full"]),"poly_depth_frac_at_1hz":m(rows["poly_1hz"]),
            "kalshi_depth_frac_ticker_1hz":m(rows["k_ticker"]),"kalshi_depth_frac_full_book":m(rows["k_book"]),
            "gross_cents_ticker":round((m(rows["gross_tick"]) or 0)*100,2),"gross_cents_full_book":round((m(rows["gross_book"]) or 0)*100,2) if rows["gross_book"] else None,
            "follower_kalshi_share_ticker":round(sum(1 for x in rows["foll_tick"] if x=="kalshi")/len(rows["foll_tick"]),3) if rows["foll_tick"] else None,
            "follower_kalshi_share_full_book":round(sum(1 for x in rows["foll_book"] if x=="kalshi")/len(rows["foll_book"]),3) if rows["foll_book"] else None}
        print(pr["label"], json.dumps(res[list(res)[-1]]), flush=True)
json.dump({"note":"medians per contract; mirrors build_harvest definitions, varies only sampling","results":res},open(OUT,"w"),indent=1)
print("wrote",OUT)
print("DONE",flush=True)
