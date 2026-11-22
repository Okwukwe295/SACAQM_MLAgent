"""Audit immutable local exports and resume source reconciliation by sensor and month."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import os
from datetime import datetime, timezone

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw_data"
# Last completed UTC hour at snapshot design (20 Nov 00:25 SAST).
END = pd.Timestamp("2026-11-19 22:00")
START = pd.Timestamp("2026-03-01")
REVISION = os.environ.get("SACAQM_REVISION","v1")
if not re.fullmatch(r"v[1-9][0-9]*",REVISION):
    raise ValueError("SACAQM_REVISION must have the form v1, v2, ...")
VERSION = "20260301_20261119T2200Z_"+REVISION
RESULT = ROOT / "results" / "coverage" / VERSION
CACHE = RAW / "reconciliation" / "20260301_20261119T2200Z_v1"
DERIVED = ROOT / "data" / "derived" / VERSION
KEYS = ["sensor_id","timestamp","pm2p5"]
URL = "https://sacaqm.web.cern.ch/dbread.php"


def digest(path):
    with path.open("rb") as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
        return h.hexdigest()


def read_rows(path):
    return pd.read_csv(path,usecols=KEYS,dtype={"sensor_id":"string"})


def existing():
    return sorted(p for p in RAW.glob("*_data.csv") if p.is_file())


def roster():
    # Reuse the notebook's authorised request roster plus known metadata identifiers.
    import ast
    cells = json.loads((ROOT/"eda.ipynb").read_text(encoding="utf8"))["cells"]
    sensors = set(pd.read_csv(ROOT/"sacaqm_dashboard_sensor_metadata.csv",dtype=str).sensor_id.dropna())
    for c in cells:
        src = "".join(c["source"]).removeprefix("%%historical\n")
        if "sensor_ids =" not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="sensor_ids" for t in node.targets) and isinstance(node.value,ast.List):
                sensors.update(ast.literal_eval(node.value))
    for f in existing():
        sensors.update(pd.read_csv(f,usecols=["sensor_id"],dtype=str).sensor_id.dropna().unique())
    return sorted({s.strip().upper() for s in sensors if re.fullmatch(r"[A-Za-z0-9]+",s.strip())})


def windows():
    for begin in pd.date_range(START,END,freq="MS"):
        yield begin,min(begin+pd.offsets.MonthBegin(),END)


def write_json(path,data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data,indent=2),encoding="utf8")
    temp.replace(path)


def reconcile(fetch=False):
    # A successful empty response is cached explicitly. A failure stays retryable.
    RESULT.mkdir(parents=True,exist_ok=True)
    CACHE.mkdir(parents=True,exist_ok=True)
    sensors = roster()
    jobs = []
    circuit_open = False
    for a,b in windows():
        for sensor in sensors:
            key = f"{a:%Y%m}_{sensor}"
            marker = CACHE/(key+".json")
            path = CACHE/(key+".csv")
            state = json.loads(marker.read_text()) if marker.exists() else {"status":"unrequested"}
            if state["status"]=="ok" and (not path.exists() or digest(path)!=state["sha256"]):
                state = {"status":"invalid_cache"}
            if fetch and not circuit_open and state["status"] not in ("ok","empty"):
                try:
                    r = requests.get(URL,params={"cmd":"get_sen55","sensor_id":sensor,
                        "from":a.strftime("%Y-%m-%dT%H:%M:%SZ"),"to":(b-pd.Timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")},timeout=(10,60))
                    r.raise_for_status()
                    data = r.json()
                    if not isinstance(data,list):
                        raise ValueError("unexpected_response")
                    state = {"status":"empty","rows":0}
                    if data:
                        frame = pd.DataFrame(data)[KEYS]
                        ts = pd.to_datetime(frame.timestamp,utc=True).dt.tz_localize(None)
                        if not frame.sensor_id.astype(str).str.upper().eq(sensor).all() or not ts.between(a,b,inclusive="left").all():
                            raise ValueError("unexpected_key_or_date")
                        temp = path.with_suffix(".part")
                        frame.to_csv(temp,index=False)
                        temp.replace(path)
                        state = {"status":"ok","rows":len(frame),"sha256":digest(path)}
                except (requests.RequestException,ValueError,KeyError) as exc:
                    state={"status":"failed","error":type(exc).__name__}
                    circuit_open=isinstance(exc,requests.ConnectionError)
                state["checked_utc"]=datetime.now(timezone.utc).isoformat()
                write_json(marker,state)
                # Keep previous failures visible after a successful retry.
                with (CACHE/"attempts.csv").open("a",newline="",encoding="utf8") as stream:
                    writer=csv.writer(stream)
                    if stream.tell()==0:
                        writer.writerow(["month","sensor_id","checked_utc","status","rows","error"])
                    writer.writerow([a.strftime("%Y-%m"),sensor,state["checked_utc"],state["status"],
                                     state.get("rows",""),state.get("error","")])
            jobs.append({"sensor_id":sensor,"month":a.strftime("%Y-%m"),**state})
    pd.DataFrame(jobs).to_csv(RESULT/"requests.csv",index=False)
    return jobs


def inputs(jobs):
    # Successful remote partitions supersede their local counterpart for this version.
    parts=[]
    complete={(j["month"],j["sensor_id"]):j for j in jobs if j["status"] in ("ok","empty")}
    sources={}
    for f in existing():
        frame=read_rows(f)
        frame["timestamp"]=pd.to_datetime(frame.timestamp,errors="raise",utc=True).dt.tz_localize(None)
        frame["sensor_id"]=frame.sensor_id.str.strip().str.upper()
        frame=frame[frame.timestamp.between(START,END,inclusive="left")]
        if complete:
            idx=pd.MultiIndex.from_arrays([frame.timestamp.dt.strftime("%Y-%m"),frame.sensor_id])
            # An apparently successful response must retain all known observations,
            # including conflicting values. A truncated or empty reply cannot erase history.
            seen=idx.isin(list(complete))
            for (month,sensor),old in frame[seen].groupby([frame.loc[seen,"timestamp"].dt.strftime("%Y-%m"),"sensor_id"]):
                job=complete[(month,sensor)]
                if job["status"]=="empty":
                    raise ValueError(f"Source returned empty for known partition {month}/{sensor}")
                fetched=read_rows(CACHE/(month.replace("-","")+"_"+sensor+".csv"))
                fetched.timestamp=pd.to_datetime(fetched.timestamp,utc=True).dt.tz_localize(None)
                key=["timestamp","pm2p5"]
                if not pd.MultiIndex.from_frame(old[key]).isin(pd.MultiIndex.from_frame(fetched[key])).all():
                    raise ValueError(f"Source response omits archived observations for {month}/{sensor}")
            frame=frame[~seen]
        sources[f.relative_to(ROOT).as_posix()]=digest(f)
        parts.append(frame)
    for j in jobs:
        if j["status"]=="ok":
            f=CACHE/(j["month"].replace("-","")+"_"+j["sensor_id"]+".csv")
            parts.append(read_rows(f))
            sources[f.relative_to(ROOT).as_posix()]=digest(f)
    raw=pd.concat(parts,ignore_index=True)
    raw.timestamp=pd.to_datetime(raw.timestamp,utc=True).dt.tz_localize(None)
    raw.sensor_id=raw.sensor_id.str.strip().str.upper()
    raw.pm2p5=pd.to_numeric(raw.pm2p5,errors="coerce")
    return raw,sources


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--fetch",action="store_true")
    print(pd.DataFrame(reconcile(parser.parse_args().fetch)).status.value_counts())
