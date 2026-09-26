from math import asin, cos, radians, sin, sqrt

import pandas as pd
import pydeck as pdk
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

# interactive map
map_col1, map_col2 = st.columns([6, 1], vertical_alignment="bottom")
with map_col1:
    st.subheader("Overlap Map")
with map_col2:
    # dropdown menu to choose light or dark map
    map_theme = st.selectbox("Map Theme", ["Dark", "Light"], label_visibility="collapsed")

# default map view centers on average of all project coordinates
center_lat = projects_df["lat_center"].mean()
center_lon = projects_df["lon_center"].mean()

# automatically assign different colors for each company
palette = [
    [0, 122, 255, 200],
    [255, 149, 0, 200],
    [52, 199, 89, 200],
    [175, 82, 222, 200],
]
unique_utils = list(projects_df["utility"].unique())
color_lookup = {u: palette[i % len(palette)] for i, u in enumerate(unique_utils)}

map_projects = projects_df.copy()
map_projects["color"] = map_projects["utility"].map(color_lookup.get)
map_projects["date_str"] = map_projects["in_service_date"].dt.strftime("%b %Y")

# colored circular nodes on map for project location
project_nodes = pdk.Layer(
    "ScatterplotLayer",
    data=map_projects,
    get_position=["lon_center", "lat_center"],
    get_fill_color="color",
    get_radius=4000,  # size of nodes in meters
    pickable=True,  # enable mouse interactions
    auto_highlight=True,  # highlight on hover
)

layers = [project_nodes]

# connecting lines between matched projects
if not overlaps_df.empty:
    overlap_arcs = pdk.Layer(
        "ArcLayer",
        data=overlaps_df,
        get_source_position=["p1_lon", "p1_lat"],
        get_target_position=["p2_lon", "p2_lat"],
        get_source_color=[0, 122, 255, 220],
        get_target_color=[255, 149, 0, 220],
        get_width=3,
        pickable=True,
        auto_highlight=True,
    )
    layers.append(overlap_arcs)

# render pydeck map
st.pydeck_chart(
    pdk.Deck(
        map_style="dark" if map_theme == "Dark" else "road",
        initial_view_state=pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=7.5,
            pitch=35,  # angle to make 3D
        ),
        layers=layers,
        tooltip={
            # type: ignore
            "html": "<b>{project_name}</b><br/>Utility: {utility}<br/>In-Service: {date_str}",
            "style": {"backgroundColor": "#1e1e1e", "color": "white", "fontSize": "13px"},
        },
    )
)

st.divider()

# raw data inspection
with st.expander("View Raw Projects Data"):
    col1, col2 = st.columns(2)
    col1.metric("Total Projects", len(projects_df))
    col2.metric("Utilities Found", ", ".join(projects_df["utility"].unique()))

    st.subheader("Raw Projects Data")
    st.dataframe(
        projects_df[["project_id", "utility", "state", "project_name", "lat_center", "lon_center", "in_service_date"]],
        use_container_width=True,
        hide_index=True,
    )
