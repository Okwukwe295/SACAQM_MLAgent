"""Rebuild the WP02 event cohort from the frozen March-July sensor exports."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import haversine_distances

OUT = Path("wp02")
H = pd.Timedelta(hours=1)
MONTHS = "march april may june july".split()


def prepare():
    # Resolve exact duplicate keys before giving each occupied five-minute bin equal weight.
    OUT.mkdir(exist_ok=True)
    keys = ["sensor_id", "timestamp"]
    raw = pd.concat([pd.read_csv(f"raw_data/{m}_data.csv", usecols=keys + ["pm2p5"],
                                dtype={"sensor_id": str}) for m in MONTHS], ignore_index=True)
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
    clean = clean.loc[clean.timestamp.between("2026-03-01","2026-08-01",inclusive="left") & clean.pm2p5.ge(0)]
    meta = pd.read_csv("sacaqm_dashboard_sensor_metadata.csv", dtype={"sensor_id": str})
    meta.sensor_id = meta.sensor_id.str.strip().str.upper()
    sites = meta[["sensor_id","station","latitude","longitude"]].drop_duplicates()
    ambiguous = sites.sensor_id.duplicated(False)
    sites[ambiguous].to_csv(OUT / "ambiguous_sites.csv",index=False)
    sites = sites[~ambiguous].dropna().set_index("sensor_id")
    sites = sites.loc[sites.index.intersection(clean.sensor_id.unique())]
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
        for n in neighbours[s]:
            p = panels[n]
            segment = p.loc[a:b]
            if len(segment)!=d or not segment.assessable.all():
                continue
            available += 1
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
        artifact = (d==1 and available==len(neighbours[s]) and available>0 and active==0
                    and first.rise>=threshold and first.x-following.x>=threshold
                    and (abs(following.z)<=1.5 or following.x<=following.mu+following.sd))
        e.update(label=("real" if matches else "fake" if artifact else "uncertain") if complete else "uncertain",
                 neighbours_available=available,matching=matches,
                 evidence_start=a-(d+2+24)*H,decision=b+(d+3)*H)
    df = pd.DataFrame(events).sort_values(["start","sensor"])
    assert not df.duplicated(["sensor","start"]).any()
    df.to_csv(OUT/"events.csv",index=False)
    audit.update(located_sensors=len(sites),events=len(df),labels=df.label.value_counts().to_dict())
    (OUT/"audit.json").write_text(json.dumps(audit,indent=2))
    return audit


if __name__ == "__main__":
    print(prepare())
