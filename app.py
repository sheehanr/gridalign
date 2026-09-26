from math import asin, cos, radians, sin, sqrt

import pandas as pd
import streamlit as st

# streamlit config
st.set_page_config(layout="wide", page_title="GridLock Coordinator")
st.title("GridLock Coordinator")


# load projects spreadsheet into a dataframe
@st.cache_data  # keep spreadsheet in memory instead of constantly reloading
def load_data():
    path = "Sperry-Tech-Challenge/Projects_Overlaps.xlsx"
    df = pd.read_excel(path, sheet_name="projects")
    df["in_service_date"] = pd.to_datetime(df["in_service_date"])

    return df


# haversine formula for finding distance between coordinates
def haversine(lat1, lon1, lat2, lon2):
    R = 3959.0  # Earth radius in mi
    lat_diff = radians(lat2 - lat1)
    lon_diff = radians(lon2 - lon1)
    a = sin(lat_diff / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_diff / 2) ** 2
    c = 2 * asin(sqrt(a))

    return R * c


# find overlapping projects and store in list
def find_overlaps(data, dist_limit, time_limit):
    records = data.to_dict("records")
    matches = []

    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            p1 = records[i]
            p2 = records[j]

            # continue if both projects are handled by the same company
            if p1["utility"] == p2["utility"]:
                continue

            dist = haversine(p1["lat_center"], p1["lon_center"], p2["lat_center"], p2["lon_center"])
            time_gap = abs((p1["in_service_date"] - p2["in_service_date"]).days)

            if dist <= dist_limit and time_gap <= time_limit:
                matches.append(
                    {
                        "Project 1": p1["project_name"],
                        "Utility 1": p1["utility"],
                        "Project 2": p2["project_name"],
                        "Utility 2": p2["utility"],
                        "Dist. (mi)": round(dist, 1),
                        "Gap (days)": time_gap,
                        "p1_lat": p1["lat_center"],  # coordinates for interactive map
                        "p1_lon": p1["lon_center"],
                        "p2_lat": p2["lat_center"],
                        "p2_lon": p2["lon_center"],
                    }
                )

    return pd.DataFrame(matches)


projects_df = load_data()

# sliders to adjust coordination thresholds
st.subheader("Coordination Thresholds")
dist_slider, time_slider = st.columns(2)
with dist_slider:
    max_dist = st.slider("Max Distance (mi)", min_value=5.0, max_value=60.0, value=30.0, step=5.0)
with time_slider:
    # largest time_gap on spreadsheet is 3074
    max_time_gap = st.slider("Max Time Gap (days)", min_value=0, max_value=3650, value=730, step=60)

overlaps_df = find_overlaps(projects_df, max_dist, max_time_gap)

st.subheader("Identified Coordination Overlaps")
st.metric("Matches Found", len(overlaps_df))

# show overlaps according to user-defined thresholds
if not overlaps_df.empty:
    st.dataframe(
        overlaps_df[["Dist. (mi)", "Gap (days)", "Project 1", "Utility 1", "Project 2", "Utility 2"]],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No overlaps found within the selected thresholds. Try adjusting the sliders above.")

# raw data inspection
col1, col2 = st.columns(2)
col1.metric("Total Projects", len(projects_df))
col2.metric("Utilities Found", ", ".join(projects_df["utility"].unique()))

st.subheader("Raw Projects Data")
st.dataframe(
    projects_df[["project_id", "utility", "state", "project_name", "lat_center", "lon_center", "in_service_date"]],
    hide_index=True,
)
