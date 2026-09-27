from math import asin, cos, log2, radians, sin, sqrt

import pandas as pd
import streamlit as st

from constants import (
    BASE_MOBILIZATION_COST,
    DATA_PATH,
    EARTH_RADIUS_MI,
    MAX_ECONOMIC_DIST_MI,
    MAX_ECONOMIC_GAP_DAYS,
)


@st.cache_data
def load_default_data():
    df = pd.read_excel(DATA_PATH, sheet_name="projects")
    df["in_service_date"] = pd.to_datetime(df["in_service_date"])
    return df


def get_combined_datasets(uploaded_files):
    """Loads default project data and appends any valid uploaded datasets."""
    combined_df = load_default_data().copy()

    if not uploaded_files:
        return combined_df

    for uploaded_file in uploaded_files:
        try:
            uploaded_file.seek(0)
            if uploaded_file.name.endswith(".xlsx"):
                uploaded_df = pd.read_excel(uploaded_file)
            else:
                uploaded_df = pd.read_csv(uploaded_file)

            # define the minimum required columns for the app to function
            required_cols = ["project_id", "utility", "project_name", "lat_center", "lon_center", "in_service_date"]
            missing_cols = [col for col in required_cols if col not in uploaded_df.columns]

            if missing_cols:
                st.toast(f"File {uploaded_file.name} missing required columns: {', '.join(missing_cols)}. Skipping.")
                continue

            # align critical types with benchmark data, coercing errors to prevent crashes on bad date strings
            uploaded_df["in_service_date"] = pd.to_datetime(uploaded_df["in_service_date"], errors="coerce")

            # ensure coordinates are parsed as float numbers (handles csv whitespace/strings)
            for coord in ["lat_center", "lon_center"]:
                if coord in uploaded_df.columns:
                    uploaded_df[coord] = pd.to_numeric(uploaded_df[coord], errors="coerce")

            # drop rows where coordinates failed to parse
            uploaded_df = uploaded_df.dropna(subset=["lat_center", "lon_center"])

            # append and drop duplicates by project_id (keeps the uploaded version)
            combined_df = pd.concat([combined_df, uploaded_df], ignore_index=True)

        except Exception as e:
            st.toast(f"Failed to parse uploaded file {uploaded_file.name}. Skipping.")
            print(f"Error parsing upload: {e}")

    if "project_id" in combined_df.columns:
        combined_df = combined_df.drop_duplicates(subset=["project_id"], keep="last")

    return combined_df


def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great-circle distance between two coordinates in miles."""
    lat_diff = radians(lat2 - lat1)
    lon_diff = radians(lon2 - lon1)
    a = sin(lat_diff / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_diff / 2) ** 2
    c = 2 * asin(sqrt(a))
    return EARTH_RADIUS_MI * c


def calculate_cost_savings(dist, time_gap, cluster_size=2):
    """Calculate the estimated cost savings ($USD) from sharing resources across utilities."""
    # beyond 25 miles or 730 days, joint staging is non-viable and yields negligible savings
    if dist > MAX_ECONOMIC_DIST_MI or time_gap > MAX_ECONOMIC_GAP_DAYS:
        return 0

    # non-linear decay curves since cost saving is greater at lower distances and time gaps
    dist_factor = max(0.0, 1.0 - (dist / MAX_ECONOMIC_DIST_MI))
    time_factor = max(0.0, 1.0 - (time_gap / MAX_ECONOMIC_GAP_DAYS))

    # base pairwise savings (labor + equipment staging)
    base_savings = BASE_MOBILIZATION_COST * (dist_factor**1.2) * (time_factor**1.0)

    return int(round(base_savings, -3))


def calculate_hub_savings(cluster_size):
    """Calculate the estimated pooled cost savings ($USD) for a multi-cluster."""
    if cluster_size <= 1:
        return 0
    if cluster_size == 2:
        return BASE_MOBILIZATION_COST

    # dynamic scaling of cost savings for sharing resources across 3+ projects
    scale_bonus = 0.25 * log2(cluster_size - 1)
    multiplier = min(1.55, 1.00 + scale_bonus)  # hard-capped at 1.55x

    return int(round(BASE_MOBILIZATION_COST * multiplier, -3))


def assign_criticality_tier(savings, dist, time_gap):
    """Assign an actionable 'criticality-tier' based on cost savings and operational window."""
    if savings == 0:
        return "Negligible Savings"

    if savings >= 750_000 or (dist <= 10.0 and time_gap <= 180):
        return "Tier 1 (High)"
    elif savings >= 250_000:
        return "Tier 2 (Moderate)"
    else:
        return "Tier 3 (Low)"


def find_overlaps(data, dist_limit, time_limit):
    """Identify projects from different utilities that overlap in time and space and group multi-clusters into hubs."""
    records = data.to_dict("records")
    raw_matches = []

    # compare every unique pair of projects to find overlaps
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            p1 = records[i]
            p2 = records[j]

            # skip checking if they belong to the same utility company
            if p1["utility"] == p2["utility"]:
                continue

            dist = haversine(p1["lat_center"], p1["lon_center"], p2["lat_center"], p2["lon_center"])
            time_gap = abs((p1["in_service_date"] - p2["in_service_date"]).days)

            if dist <= dist_limit and time_gap <= time_limit:
                raw_matches.append(
                    {
                        "Project 1": p1["project_name"],
                        "Utility 1": p1["utility"],
                        "Project 2": p2["project_name"],
                        "Utility 2": p2["utility"],
                        "Dist. (mi)": round(dist, 1),
                        "Gap (days)": time_gap,
                        "p1_lat": p1["lat_center"],
                        "p1_lon": p1["lon_center"],
                        "p2_lat": p2["lat_center"],
                        "p2_lon": p2["lon_center"],
                    }
                )

    if not raw_matches:
        return pd.DataFrame(), {}

    df = pd.DataFrame(raw_matches)

    # build adjacency network to detect contiguous multi-project regional clusters
    adjacency = {}
    for _, row in df.iterrows():
        p1, p2 = row["Project 1"], row["Project 2"]
        adjacency.setdefault(p1, set()).add(p2)
        adjacency.setdefault(p2, set()).add(p1)

    # extract connected components to identify distinct regional staging hubs
    visited = set()
    hubs = []
    for project in adjacency:
        if project not in visited:
            component = set()
            queue = [project]
            visited.add(project)
            while queue:
                curr = queue.pop(0)
                component.add(curr)
                for neighbor in adjacency[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            hubs.append(component)

    # sort clusters so largest cluster is always hub a
    hubs = sorted(hubs, key=len, reverse=True)

    # map each project to its designated hub label and store hub metrics
    project_to_hub = {}
    hub_summary = {}
    for idx, hub_projects in enumerate(hubs):
        hub_name = f"Hub {idx + 1}"  # Hub 1, Hub 2, Hub 3...
        for p in hub_projects:
            project_to_hub[p] = hub_name

        hub_summary[hub_name] = {
            "project_count": len(hub_projects),
            "projects": hub_projects,
            "hub_savings": calculate_hub_savings(len(hub_projects)),
        }

    savings_list = []
    tiers_list = []
    hubs_list = []

    # compute pairwise bilateral savings and assign hub associations
    for _, row in df.iterrows():
        hub_id = project_to_hub.get(row["Project 1"], "Independent")
        savings = calculate_cost_savings(row["Dist. (mi)"], row["Gap (days)"])
        tier = assign_criticality_tier(savings, row["Dist. (mi)"], row["Gap (days)"])

        hubs_list.append(hub_id)
        savings_list.append(savings)
        tiers_list.append(tier)

    df["Hub"] = hubs_list
    df["Savings ($)"] = savings_list
    df["Criticality"] = tiers_list

    return df, hub_summary
