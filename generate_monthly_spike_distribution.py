import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Update this path if needed
events_path = Path("data/derived/20260301_20261119T2200Z_v1/events.csv")

df = pd.read_csv(events_path)

# Adjust the event-start column name if your file uses a different one
candidate_cols = ["start", "event_start", "event_start_time", "start_time"]
start_col = next((c for c in candidate_cols if c in df.columns), None)
if start_col is None:
    raise ValueError(f"Could not find an event start column. Available columns: {list(df.columns)}")

df[start_col] = pd.to_datetime(df[start_col])
df["month"] = df[start_col].dt.to_period("M").astype(str)

monthly_counts = df.groupby("month").size().reset_index(name="events")
print(monthly_counts)

ax = monthly_counts.plot(x="month", y="events", kind="bar", figsize=(8, 5), legend=False)
ax.set_title("Monthly Spike-Event Distribution")
ax.set_xlabel("Month")
ax.set_ylabel("Number of Events")
plt.tight_layout()
plt.savefig("monthly_spike_event_distribution.png", dpi=200, bbox_inches="tight")
plt.show()
