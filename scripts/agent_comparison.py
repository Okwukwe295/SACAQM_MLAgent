"""Read-only station-hour comparison. No agent application imports or database writes."""
import json
from pathlib import Path
import pandas as pd
from scripts import ingest

OUT=ingest.ROOT/"results"/"agent"/ingest.VERSION


def match(events,investigations,stations,timestamp_basis):
    # Permit matching only after the source clock relationship has been established.
    if timestamp_basis not in ("same_clock_confirmed","conditional_export"):
        raise ValueError("Matching requires a verified common source clock")
    idx={}
    for row in stations:
        for sensor in row.get("sensorIds",[]):
            idx.setdefault(str(sensor).strip().upper(),set()).add(str(row["_id"]))
    intervals={}
    for e in events.itertuples():
        mapped=idx.get(e.sensor,set())
        if len(mapped)!=1: continue
        station=next(iter(mapped))
        for hour in pd.date_range(e.start,e.end,freq="h"):
            intervals.setdefault((station,hour),[]).append((e.sensor,e.start))
    rows=[]
    for inv in investigations:
        t=pd.Timestamp(inv["timestamp"])
        if t.tzinfo is not None:t=t.tz_convert("UTC").tz_localize(None)
        candidates=intervals.get((str(inv.get("station_id")),t.floor("h")),[])
        row=dict(investigation=str(inv["_id"]),timestamp=t,decision=inv.get("decision"),review=inv.get("human_verdict"),correction=inv.get("correct_decision"))
        row["status"]="unmatched" if not candidates else "ambiguous" if len(candidates)>1 else "matched"
        if len(candidates)==1:row["sensor"],row["start"]=candidates[0]
        rows.append(row)
    frame=pd.DataFrame(rows,columns=["investigation","timestamp","decision","review","correction","status","sensor","start"])
    overlaps=frame.status.eq("matched") & frame.duplicated(["sensor","start"],keep=False)
    frame.loc[overlaps,"status"]="multiple_investigations"
    return frame



def compare_exports():
    """Validate the local snapshot, then audit linkage under explicit clock scenarios."""
    source = ingest.ROOT/"data/derived/agent_exports"
    out = OUT/"export_20261120"
    out.mkdir(parents=True,exist_ok=True)
    hashes = {p.name:ingest.digest(p) for p in source.iterdir() if p.is_file()}
    summary = json.loads((source/"export_summary.json").read_text())
    a = pd.read_csv(source/"agent_events.csv",dtype=str,keep_default_na=False)
    m = pd.read_csv(source/"station_sensor_map.csv",dtype=str,keep_default_na=False)
    a.timestamp = pd.to_datetime(a.timestamp,errors="raise")
    assert a.agent_event_id.is_unique and a.agent_event_id.ne("").all()
    assert a.station_id.ne("").all() and a.metric.eq("pm2p5").all()
    assert len(a)==summary["agent_event_count"] and len(m)==summary["station_sensor_mapping_rows"]
    assert m.station_id.nunique()==summary["station_count"]
    assert a.decision.value_counts().to_dict()==summary["event_decisions"]
    assert a.human_verdict.value_counts().to_dict()==summary["human_review_status"]
    assert a.timestamp.dt.strftime("%Y-%m").value_counts().to_dict()==summary["events_by_source_timestamp_month"]
    assert pd.to_numeric(a.confidence).between(0,100).all()
    a["missing_measurement"]=pd.to_numeric(a.value,errors="coerce").isna()
    assert a.loc[a.human_verdict=="wrong","correct_decision"].isin(["alert","no_alert"]).all()
    assert a.loc[a.human_verdict!="wrong","correct_decision"].eq("").all()
    m.sensor_id=m.sensor_id.str.strip().str.upper()
    assert m.sensor_id.ne("").all() and m.station_id.ne("").all()
    assert pd.to_numeric(m.latitude).between(-90,90).all() and pd.to_numeric(m.longitude).between(-180,180).all()

    # Compare both directions of the mapping and the coordinates used by the model.
    meta=pd.read_csv(ingest.ROOT/"sacaqm_dashboard_sensor_metadata.csv",dtype={"sensor_id":str})
    meta.sensor_id=meta.sensor_id.str.strip().str.upper()
    meta=meta[["sensor_id","latitude","longitude"]].drop_duplicates()
    ambiguous_meta=set(meta.loc[meta.sensor_id.duplicated(False),"sensor_id"])
    sites=m.merge(meta.drop_duplicates("sensor_id"),on="sensor_id",how="left",suffixes=("","_model"))
    sites["status"]="eligible"
    mismatch=(pd.to_numeric(sites.latitude)-sites.latitude_model).abs().gt(.0001) | (pd.to_numeric(sites.longitude)-sites.longitude_model).abs().gt(.0001)
    sites.loc[mismatch,"status"]="coordinate_discrepancy"
    sites.loc[sites.latitude_model.isna()|sites.longitude_model.isna(),"status"]="no_model_site"
    sites.loc[sites.sensor_id.isin(ambiguous_meta),"status"]="ambiguous_model_site"
    sites.loc[sites.groupby("sensor_id").station_id.transform("nunique")>1,"status"]="sensor_multiple_stations"
    sites.loc[sites.groupby("station_id").sensor_id.transform("nunique")>1,"status"]="station_multiple_sensors"
    sites.to_csv(out/"station_mapping_audit.csv",index=False)
    status=sites.groupby("station_id").status.first()
    a["identity"]=a.station_id.map(status).fillna("unmapped_station")
    good=sites[sites.status=="eligible"]
    stations=[{"_id":r.station_id,"sensorIds":[r.sensor_id]} for r in good.itertuples()]
    a["hour"]=a.timestamp.dt.floor("h")
    groups=a.groupby(["station_id","hour"])
    a["station_hour_count"]=groups.agent_event_id.transform("size")
    a["station_hour_conflict"]=groups.decision.transform("nunique").gt(1)
    a["reviewed"]=a.human_verdict.isin(["correct","wrong"])
    a["reviewed_action"]=a.correct_decision.where(a.human_verdict.eq("wrong"),a.decision.where(a.reviewed,""))
    event_file=ingest.DERIVED/"events.csv"
    events=pd.read_csv(event_file,parse_dates=["start","end"])
    model_dir=ingest.ROOT/"results/wp03"/ingest.VERSION/"local_through_september"
    assert ingest.digest(event_file)==json.loads((model_dir/"design.json").read_text())["dataset_hash"]
    pred=pd.read_csv(model_dir/"predictions.csv",parse_dates=["start","end"])
    keys=["sensor","start"]
    assert not events.duplicated(keys).any() and not pred.duplicated(keys+["arm","model"]).any()
    last=pd.Timestamp(json.loads((ingest.RESULT/"manifest.json").read_text())["observed_end"])
    first=pd.to_datetime(pd.read_csv(ingest.RESULT/"monthly.csv")["first"]).min()
    scenarios=[]
    for shift in [0,-2,2]:
        data=a.rename(columns={"agent_event_id":"_id"}).copy()
        data.timestamp+=pd.Timedelta(hours=shift)
        rec=match(events,data.to_dict("records"),stations,"conditional_export")
        rec=rec.merge(a,left_on="investigation",right_on="agent_event_id",validate="one_to_one",suffixes=("_aligned",""))
        rec.loc[rec.identity!="eligible","status"]=rec.identity
        outside=(rec.timestamp_aligned<first.floor("h"))|(rec.timestamp_aligned>=last.ceil("h"))
        rec.loc[(rec.status=="unmatched")&outside,"status"]="outside_period"
        rec["offset_hours"]=shift
        scenarios.append(rec)
    sensitivity=[]
    for rec in scenarios:
        single=rec[rec.status=="matched"]
        repeated=rec[rec.status=="multiple_investigations"]
        ng=repeated.groupby(keys).decision.nunique()
        sensitivity.append(dict(offset_hours=int(rec.offset_hours.iloc[0]),unique_pairs=len(single),
            reviewed_pairs=int(single.reviewed.sum()),repeated_events=len(ng),conflicting_repeated_events=int((ng>1).sum()),
            events_without_overlap=len(events)-len(single)-len(ng)))
    pd.DataFrame(sensitivity).to_csv(out/"clock_sensitivity.csv",index=False)
    rec=scenarios[0]
    rec.to_csv(ingest.DERIVED/"agent_investigation_linkage.csv",index=False)
    rec.groupby(["status","human_verdict"]).size().rename("investigations").to_csv(out/"coverage_by_review.csv")
    a.groupby(["station_hour_count","station_hour_conflict"]).size().rename("investigations").to_csv(out/"repeated_station_hours.csv")
    pair=rec[rec.status=="matched"].merge(events[keys+["label"]],on=keys,validate="one_to_one")
    overlap=pair.merge(pred[keys+["arm","model","prediction"]],on=keys,how="inner",validate="one_to_many")
    pair.to_csv(ingest.DERIVED/"agent_unique_pairs.csv",index=False)
    overlap.to_csv(ingest.DERIVED/"agent_model_pairs.csv",index=False)
    pair.groupby(["label","decision","human_verdict","reviewed_action"]).size().rename("pairs").to_csv(out/"agent_weak_labels.csv")
    overlap.groupby(["arm","model","label","decision","prediction","human_verdict","reviewed_action"]).size().rename("pairs").to_csv(out/"three_way_comparison.csv")
    review=a[a.reviewed]
    review.groupby(["human_verdict","decision","reviewed_action"]).size().rename("investigations").to_csv(out/"reviewed_decisions.csv")
    result=dict(missing_measurement_values=int(a.missing_measurement.sum()),source_hashes=hashes,investigations=len(a),reviewed=len(review),rebuilt_events=len(events),
        independently_verified_event_links=0,conditional_unique_pairs=len(pair),events_without_unique_pair=len(events)-len(pair),
        reviewed_unique_pairs=int(pair.reviewed.sum()),heldout_unique_events=len(overlap[keys].drop_duplicates()),
        reviewed_heldout_events=len(overlap[overlap.reviewed][keys].drop_duplicates()),
        statuses=rec.status.value_counts().to_dict(),reviewed_statuses=rec[rec.reviewed].status.value_counts().to_dict(),
        clock_scenarios=sensitivity)
    ingest.write_json(out/"summary.json",result)
    assert hashes=={p.name:ingest.digest(p) for p in source.iterdir() if p.is_file()}
    return result


if __name__=="__main__":
    print(json.dumps(compare_exports(),indent=2))

