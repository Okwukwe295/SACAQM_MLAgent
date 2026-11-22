"""Produce blinded target and neighbour traces for the 30 historical review cases."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import haversine_distances
from wp02_prepare import MONTHS, OUT, H


def review_packets():
    cases = pd.read_csv(OUT/"review_cases.csv",parse_dates=["event_start_time","event_end_time"])
    sites = pd.read_csv("sacaqm_dashboard_sensor_metadata.csv",dtype={"sensor_id":str})
    sites = sites[["sensor_id","station","latitude","longitude"]].drop_duplicates()
    sites = sites[~sites.sensor_id.duplicated(False)].dropna().set_index("sensor_id")
    chunks = []
    for month in MONTHS:
        raw = pd.read_csv(f"raw_data/{month}_data.csv",usecols=["sensor_id","timestamp","pm2p5"],
                          dtype={"sensor_id":str},parse_dates=["timestamp"])
        for case in cases.itertuples():
            if case.sensor_id not in sites.index:
                continue
            coords = np.radians(sites[["latitude","longitude"]])
            distances = haversine_distances(coords,coords.loc[[case.sensor_id]])[:,0]*6371
            select = raw.timestamp.between(case.event_start_time-12*H,case.event_end_time+13*H)
            trace = raw[select & raw.sensor_id.isin(sites.index[distances<=5])].copy()
            if len(trace):
                trace["case"] = case.case
                chunks.append(trace)
    traces = pd.concat(chunks).drop_duplicates()
    traces = traces[~traces.duplicated(["case","sensor_id","timestamp"],keep=False) & traces.pm2p5.ge(0)]
    with PdfPages(OUT/"blinded_review.pdf") as pdf:
        for case in cases.itertuples():
            fig,ax = plt.subplots(figsize=(10,5))
            for sensor,g in traces[traces.case==case.case].groupby("sensor_id"):
                is_target = sensor==case.sensor_id
                ax.scatter(g.timestamp,g.pm2p5,s=6 if is_target else 3,
                           color="black" if is_target else "steelblue",alpha=.85 if is_target else .3)
            ax.axvspan(case.event_start_time,case.event_end_time+H,color="orange",alpha=.16)
            ax.set(title=f"Case {case.case} | {case.sensor_id} | {case.event_start_time:%Y-%m-%d %H:%M}",
                   ylabel="PM2.5 (µg/m³)",xlabel="Target in black, nearby sensors in blue. Shading marks candidate hours.")
            fig.autofmt_xdate()
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)


if __name__ == "__main__":
    review_packets()
