"""Shared preparation for bounded snapshots; legacy mode verifies the frozen implementation."""
import json
import tempfile
import platform
from importlib.metadata import version
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import haversine_distances
from scripts import ingest

H = pd.Timedelta(hours=1)


def build(raw, cutoff, OUT, legacy=False):
    OUT.mkdir(exist_ok=True,parents=True)
    keys = ["sensor_id","timestamp"]
    raw.sensor_id = raw.sensor_id.str.strip().str.upper()
    raw.timestamp = pd.to_datetime(raw.timestamp, errors="coerce")
    raw.pm2p5 = pd.to_numeric(raw.pm2p5, errors="coerce")
    audit = {"raw_rows": len(raw), "raw_sensors": raw.sensor_id.nunique()}
    raw = raw.dropna(subset=keys)
    conflicts = raw.groupby(keys).pm2p5.nunique().loc[lambda x: x > 1]
    audit.update(extra_keys=int(raw.duplicated(keys).sum()), conflicting_keys=len(conflicts))
    conflicts.to_csv(OUT / "conflicting_keys.csv")
    clean = raw.dropna().drop_duplicates(keys).set_index(keys).drop(conflicts.index)
    clean = clean.reset_index()
    clean = clean.loc[clean.timestamp.between(ingest.START,cutoff,inclusive="left") & clean.pm2p5.ge(0)]
    meta = pd.read_csv(ingest.ROOT/"sacaqm_dashboard_sensor_metadata.csv", dtype={"sensor_id": str})
    meta.sensor_id = meta.sensor_id.str.strip().str.upper()
    sites = meta[["sensor_id","station","latitude","longitude"]].drop_duplicates()
    ambiguous = sites.sensor_id.duplicated(False)
    sites[ambiguous].to_csv(OUT / "ambiguous_sites.csv",index=False)
    sites = sites[~ambiguous].dropna().set_index("sensor_id")
    if not sites.latitude.between(-90,90).all() or not sites.longitude.between(-180,180).all():
        raise ValueError("Invalid station coordinates")
    sites = sites.loc[sites.index.intersection(clean.sensor_id.unique())]
    first_seen = clean.groupby("sensor_id").timestamp.min()
    km = haversine_distances(np.radians(sites[["latitude","longitude"]])) * 6371
    neighbours = {s: sites.index[(km[i] <= 5) & (sites.index != s)].tolist()
                  for i,s in enumerate(sites.index)}
    clean["slot"] = clean.timestamp.dt.floor("5min")
    bins = clean.groupby(["sensor_id","slot"]).pm2p5.mean().reset_index()
    hours = bins.groupby(["sensor_id",bins.slot.dt.floor("h")]).pm2p5.agg(["mean","count"])
    panels, events = {}, []
    for sensor in sites.index:
        p = hours.loc[sensor].asfreq("h")
        x = p["mean"].where(p["count"] >= 10)
        baseline = x.shift().rolling(24,min_periods=6)
        p["x"], p["mu"], p["sd"] = x, baseline.mean(), baseline.std()
        p["z"] = (x-p.mu)/p.sd.clip(lower=2)
        p["rise"] = x.diff()
        p["assessable"] = p.z.notna() & p.rise.notna()
        p["spike"] = (p.z > 3) & (p.rise >= 10)
        runs = p.spike.ne(p.spike.shift()).cumsum()
        p["duration"] = p.spike.groupby(runs).transform("sum")
        panels[sensor] = p
        for _,g in p[p.spike].groupby(runs):
            events.append(dict(sensor=sensor,start=g.index.min(),end=g.index.max(),
                               duration=len(g),peak=g.x.max(),event_mean=g.x.mean(),
                               prior_mean=g.mu.iloc[0],prior_sd=g.sd.iloc[0]))
    # Bound neighbour evidence to a fixed window. Only fully observed runs can confirm duration.
    for e in events:
        s,a,b,d = (e[k] for k in ("sensor","start","end","duration"))
        target = panels[s]
        following = target.reindex([b+H]).iloc[0]
        previous = target.reindex([a-H]).iloc[0]
        complete = bool(previous.assessable == True and following.assessable == True)
        available = active = matches = 0
        eligible = [n for n in neighbours[s] if legacy or first_seen[n] < a+H]
        distances, concentrations = [], []
        for n in eligible:
            p = panels[n]
            segment = p.loc[a:b]
            if len(segment)!=d or not segment.assessable.all():
                continue
            available += 1
            distances.append(km[sites.index.get_loc(s),sites.index.get_loc(n)])
            concentrations.append(segment.x.mean())
            overlap = segment[segment.spike]
            active += int(len(overlap)>0)
            for t in overlap.index:
                local = p.loc[t-(d+2)*H:t+(d+2)*H]
                left = local.loc[:t].loc[lambda f: ~f.spike]
                right = local.loc[t:].loc[lambda f: ~f.spike]
                if left.empty or right.empty:
                    continue
                l,r = left.iloc[-1],right.iloc[0]
                if l.assessable and r.assessable and abs((r.name-l.name)/H-1-d)<=1:
                    matches += 1
                    break
        first = target.loc[a]
        threshold = max(10,2*first.sd)
        artifact = (d==1 and available==len(eligible) and available>0 and active==0
                    and first.rise>=threshold and first.x-following.x>=threshold
                    and (abs(following.z)<=1.5 or following.x<=following.mu+following.sd))
        # For colocated instruments use their mean, avoiding division by zero.
        dist = np.asarray(distances)
        vals = np.asarray(concentrations)
        e["idw_pm25"] = (vals[dist==0].mean() if (dist==0).any() else
                          np.average(vals,weights=1/dist**2) if len(dist) else np.nan)
        if not legacy and b+(d+3)*H > cutoff:
            complete = False
        e.update(label=("real" if matches else "fake" if artifact else "uncertain") if complete else "uncertain",
                 neighbours_available=available,matching=matches,
                 evidence_start=a-(d+2+24)*H,decision=b+(d+3)*H)
    hourly = pd.concat(panels,names=["sensor","timestamp"]).reset_index()
    hourly.to_csv(OUT/"hourly.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    df = pd.DataFrame(events).sort_values(["start","sensor"])
    assert not df.duplicated(["sensor","start"]).any()

    df.to_csv(OUT/"events.csv",index=False)
    audit.update(located_sensors=len(sites),events=len(df),labels=df.label.value_counts().to_dict())
    return df,audit


def benchmark_check(raw):
    # Use only the original immutable monthly inputs for the equivalence check.
    with tempfile.TemporaryDirectory() as folder:
        frame,_ = build(raw,pd.Timestamp("2026-08-01"),Path(folder),legacy=True)
        expected=pd.read_csv(ingest.ROOT/"wp02/events.csv",parse_dates=["start","end","decision","evidence_start"])
        pd.testing.assert_frame_equal(frame[expected.columns].reset_index(drop=True),expected,check_dtype=False)


def prepare():
    jobs=ingest.reconcile()
    raw,sources=ingest.inputs(jobs)
    data=ingest.DERIVED
    result=ingest.RESULT
    # Refuse to replace an existing snapshot with a different set of source files.
    previous=result/"manifest.json"
    if previous.exists():
        known=json.loads(previous.read_text())["inputs"]
        candidate=dict(sources)
        candidate["sacaqm_dashboard_sensor_metadata.csv"]=ingest.digest(ingest.ROOT/"sacaqm_dashboard_sensor_metadata.csv")
        if known!=candidate:
            raise ValueError("Source inventory changed; select a new snapshot revision")
    df,audit=build(raw,ingest.END,data)
    # Inventory all roster days, including absent and partially sampled days.
    ids=sorted({j["sensor_id"] for j in jobs})
    days=pd.date_range(ingest.START,ingest.END.floor("D"),freq="D")
    idx=pd.MultiIndex.from_product([ids,days],names=["sensor_id","day"])
    slots=raw.dropna(subset=["pm2p5"]).loc[lambda x:x.pm2p5.ge(0)].assign(slot=lambda x:x.timestamp.dt.floor("5min"))
    coverage=slots.groupby(["sensor_id",slots.timestamp.dt.floor("D")]).slot.nunique()
    coverage.index.names=idx.names
    daily=coverage.reindex(idx,fill_value=0).rename("observed_slots").reset_index()
    daily["expected_slots"]=[min(288,int((ingest.END-d)/pd.Timedelta(minutes=5))) for d in daily.day]
    daily.to_csv(data/"sensor_day_coverage.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    rows=[]
    for a,b in ingest.windows():
        measurements=raw[raw.timestamp.between(a,b,inclusive="left")]
        events=df[df.start.between(a,b,inclusive="left")]
        counts=events.label.value_counts()
        d=daily[daily.day.between(a,b,inclusive="left")]
        rows.append(dict(month=str(a.to_period("M")),raw_rows=len(measurements),sensors=measurements.sensor_id.nunique(),
                    events=len(events),real=counts.get("real",0),fake=counts.get("fake",0),uncertain=counts.get("uncertain",0),
                    first=measurements.timestamp.min(),last=measurements.timestamp.max(),partial_sensor_days=int(d.observed_slots.between(1,d.expected_slots-1).sum()),
                    empty_sensor_days=int(d.observed_slots.eq(0).sum())))
    pd.DataFrame(rows).to_csv(result/"monthly.csv",index=False)
    sources["sacaqm_dashboard_sensor_metadata.csv"]=ingest.digest(ingest.ROOT/"sacaqm_dashboard_sensor_metadata.csv")
    audit.update(python=platform.python_version(),packages={name:version(name) for name in ("numpy","pandas","scikit-learn","requests")},
                 scripts={name:ingest.digest(ingest.ROOT/"scripts"/name) for name in ("prepare.py","ingest.py")},
                 requested_end_exclusive=str(ingest.END),observed_end=str(raw.timestamp.max()),inputs=sources,
                 request_status=pd.Series([j["status"] for j in jobs]).value_counts().to_dict(),
                 fully_reconciled=all(j["status"] in ("ok","empty") for j in jobs),
                 outputs={name:ingest.digest(data/name) for name in ("events.csv","hourly.csv.gz","ambiguous_sites.csv","conflicting_keys.csv","sensor_day_coverage.csv.gz")})
    ingest.write_json(result/"manifest.json",audit)
    return audit


if __name__=="__main__":
    prepare()
