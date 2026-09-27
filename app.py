from math import asin, cos, log2, radians, sin, sqrt

import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(layout="wide", page_title="GridAlign", initial_sidebar_state="expanded")

# --- constants ---
DATA_PATH = "data/Projects_Overlaps.xlsx"
EARTH_RADIUS_MI = 3959.0
UTILITY_COLOR_PALETTE = [
    [0, 122, 255, 200],
    [255, 215, 0, 200],
    [52, 199, 89, 200],
    [175, 82, 222, 200],
]
MAX_ECONOMIC_DIST_MI = 25.0  # transmission staging radius limit
MAX_ECONOMIC_GAP_DAYS = 730  # in-service date gap limit
BASE_MOBILIZATION_COST = 1_800_000  # baseline combined equipment and labor cost


# --- data processing ---
@st.cache_data
def load_data():
    df = pd.read_excel(DATA_PATH, sheet_name="projects")
    df["in_service_date"] = pd.to_datetime(df["in_service_date"])
    return df


def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great-circle distance between two coordinates in miles."""
    lat_diff = radians(lat2 - lat1)
    lon_diff = radians(lon2 - lon1)
    a = sin(lat_diff / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_diff / 2) ** 2
    c = 2 * asin(sqrt(a))
    return EARTH_RADIUS_MI * c


def calculate_cost_savings(dist, time_gap, cluster_size=2):
    """Calculate the estimated cost savings ($USD) from sharing resources across utilities."""
    # beyond 25 miles or 730 days, joint staging is non-viable and yields no savings
    if dist > MAX_ECONOMIC_DIST_MI or time_gap > MAX_ECONOMIC_GAP_DAYS:
        return 0

    # non-linear decay curves since cost saving is greater at lower distances and time gaps
    dist_factor = max(0.0, 1.0 - (dist / MAX_ECONOMIC_DIST_MI))
    time_factor = max(0.0, 1.0 - (time_gap / MAX_ECONOMIC_GAP_DAYS))

    # base pairwise savings (labor + equipment staging)
    base_savings = BASE_MOBILIZATION_COST * (dist_factor**1.2) * (time_factor**1.0)

    # dynamic scaling of cost savings for sharing resources across 3+ projects
    if cluster_size <= 2:
        multiplier = 1.00  # base cost savings
    else:
        # diminishing returns with each additional project
        scale_bonus = 0.25 * log2(cluster_size - 1)
        multiplier = min(1.55, 1.00 + scale_bonus)  # hard-capped at 1.55x

    return int(round(base_savings * multiplier, -3))


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
    """Identify projects from different utilities that overlap in time and space."""
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
        return pd.DataFrame()

    df = pd.DataFrame(raw_matches)

    # build adjacency network to detect 3+ project regional clusters
    adjacency = {}
    for _, row in df.iterrows():
        p1, p2 = row["Project 1"], row["Project 2"]
        adjacency.setdefault(p1, set()).add(p2)
        adjacency.setdefault(p2, set()).add(p1)

    savings_list = []
    tiers_list = []

    # compute savings using the dynamic cluster size
    for _, row in df.iterrows():
        connected = adjacency.get(row["Project 1"], set()).union(adjacency.get(row["Project 2"], set()))
        connected.add(row["Project 1"])
        connected.add(row["Project 2"])
        cluster_size = len(connected)

        savings = calculate_cost_savings(row["Dist. (mi)"], row["Gap (days)"], cluster_size=cluster_size)
        tier = assign_criticality_tier(savings, row["Dist. (mi)"], row["Gap (days)"])

        savings_list.append(savings)
        tiers_list.append(tier)

    df["Savings ($)"] = savings_list
    df["Criticality"] = tiers_list

    return df


# --- ui components ---
def inject_custom_css():
    st.markdown(
        """
        <style>
            /* manage spacing at top and bottom of page */
            .block-container {
                padding-top: 3.75rem !important;
                padding-bottom: 2rem !important;
            }

            /* sidebar border and default width */
            section[data-testid="stSidebar"] {
                border-right: 2px solid #27272a !important;
                min-width: 360px !important;
                max-width: 360px !important;
            }

            /* sidebar header styling and cushion underneath */
            section[data-testid="stSidebar"] h2 {
                font-size: 1.65rem !important;
                font-weight: 700 !important;
                margin-top: 0.25rem !important;
                margin-bottom: 1.5rem !important;
            }

            /* space above and below the divider (separates sliders from pills) */
            section[data-testid="stSidebar"] hr {
                margin-top: 2rem !important;
                margin-bottom: 1.75rem !important;
                border-color: #27272a !important;
            }

            /* space between the two pill groups */
            section[data-testid="stSidebar"] [data-testid="stPills"] {
                margin-bottom: 1.5rem !important;
            }

            /* ensure widget labels stretch across the full sidebar width */
            section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
                display: flex !important;
                width: 100% !important;
                justify-content: space-between !important;
                align-items: center !important;
            }

            /* sliders already have a full-width container, keep their label width natural */
            section[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stWidgetLabel"] {
                width: auto !important;
            }

            /* pin all question mark icons to the far right edge */
            section[data-testid="stSidebar"] [data-testid="stTooltipHoverTarget"] {
                margin-left: auto !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_title():
    st.markdown(
        "<h1 style='text-align: center; font-size: 3.5rem; font-weight: 700; margin-top: 0rem; margin-bottom: 2rem;'>"
        "GridAlign</h1>",
        unsafe_allow_html=True,
    )


def render_sidebar(available_utilities):
    with st.sidebar:
        st.header("Filter Results")

        # sliders for distance and time gap
        max_dist = st.slider(
            "Max Distance (mi)",
            min_value=5.0,
            max_value=60.0,
            value=25.0,
            step=5.0,
            help="Negligible cost savings past 25 miles",
        )
        max_time_gap = st.slider(
            "Max Time Gap (days)",
            min_value=0,
            max_value=1200,
            value=730,
            step=10,
            help="Negligible cost savings past 730 days (2 years)",
        )

        # clickable pills for tiers
        tier_options = ["Tier 1 (High)", "Tier 2 (Moderate)", "Tier 3 (Low)", "Negligible Savings"]
        selected_tiers = st.pills(
            "Criticality Tiers",
            options=tier_options,
            default=tier_options,
            selection_mode="multi",
            help=r"- **Tier 1:** $\ge$\$750k savings or high proximity (<10 mi, <180 d)" + "\n"
            r"- **Tier 2:** \$250k–\$750k savings" + "\n"
            r"- **Tier 3:** <\$250k savings" + "\n"
            r"- **Negligible:** Beyond economic limits (\$0 savings)",
        )
        selected_tiers = list(selected_tiers or [])  # fallback to empty list if user unselects all

        # clickable pills for utilities
        selected_utilities = st.pills(
            "Participating Utilities",
            options=available_utilities,
            default=available_utilities,
            selection_mode="multi",
        )
        selected_utilities = list(selected_utilities or [])

    return max_dist, max_time_gap, selected_utilities, selected_tiers


def build_map_layers(projects_df, overlaps_df, color_lookup, active_projects, selected_overlaps=None):
    """Constructs the PyDeck map layers for projects and their overlaps."""
    map_projects = projects_df.copy()
    map_projects["color"] = map_projects["utility"].map(color_lookup.get)

    selected_project_names = set()
    if selected_overlaps is not None and not selected_overlaps.empty:
        selected_project_names = set(selected_overlaps["Project 1"]).union(set(selected_overlaps["Project 2"]))

    # helper to dynamically set node opacities depending on what is selected
    def get_node_color(row):
        base = row["color"][:3]

        # if user clicked specific rows in the table, highlight those and heavily dim the rest
        if selected_overlaps is not None and not selected_overlaps.empty:
            return base + [255] if row["project_name"] in selected_project_names else base + [40]

        # if nothing is clicked, just slightly dim projects that don't have any overlaps at all
        return base + [220] if row["project_name"] in active_projects else base + [40]

    map_projects["color"] = map_projects.apply(get_node_color, axis=1)

    # increase the radius of selected nodes so they stand out more clearly
    map_projects["radius"] = map_projects["project_name"].apply(
        lambda name: 7500 if (selected_overlaps is not None and name in selected_project_names) else 5000
    )

    map_projects["date_str"] = map_projects["in_service_date"].dt.strftime("%b %Y")
    map_projects["tip_title"] = map_projects["project_name"]
    map_projects["tip_sub"] = "Utility: " + map_projects["utility"]
    map_projects["tip_body"] = "In-Service: " + map_projects["date_str"]

    layers = []

    project_nodes = pdk.Layer(
        "ScatterplotLayer",
        data=map_projects,
        get_position=["lon_center", "lat_center"],
        get_fill_color="color",
        get_radius="radius",
        radius_min_pixels=5,
        radius_max_pixels=14,
        pickable=True,
        auto_highlight=True,
        parameters={"depthTest": False},  # prevents visual flickering between overlapping dots
    )
    layers.append(project_nodes)

    if not overlaps_df.empty:
        map_overlaps = overlaps_df.copy()

        # check for negligible relations
        is_negligible = map_overlaps["Criticality"].str.contains("Negligible", case=False, na=False)

        # base widths: slimmer for negligible, default for viable
        map_overlaps["arc_width"] = 2.0
        map_overlaps.loc[is_negligible, "arc_width"] = 1.5

        # base colors: map utility colors
        map_overlaps["color_p1"] = map_overlaps["Utility 1"].map(color_lookup.get)
        map_overlaps["color_p2"] = map_overlaps["Utility 2"].map(color_lookup.get)

        # mute negligible arcs to faint gray
        map_overlaps.loc[is_negligible, "color_p1"] = map_overlaps.loc[is_negligible, "color_p1"].apply(
            lambda _: [190, 195, 205, 80]
        )
        map_overlaps.loc[is_negligible, "color_p2"] = map_overlaps.loc[is_negligible, "color_p2"].apply(
            lambda _: [190, 195, 205, 80]
        )

        # visually emphasize the connecting arcs for any overlaps selected in the table
        if selected_overlaps is not None and not selected_overlaps.empty:
            selected_ranks = set(selected_overlaps["Rank"])
            is_match = map_overlaps["Rank"].isin(selected_ranks)

            # increased arc width and opacity for selected rows
            map_overlaps.loc[is_match, "arc_width"] = 3.5
            map_overlaps.loc[is_match, "color_p1"] = map_overlaps.loc[is_match, "color_p1"].apply(
                lambda c: c[:3] + [255]
            )
            map_overlaps.loc[is_match, "color_p2"] = map_overlaps.loc[is_match, "color_p2"].apply(
                lambda c: c[:3] + [255]
            )

            # decreased arc opacity for unselected rows
            map_overlaps.loc[~is_match, "color_p1"] = map_overlaps.loc[~is_match, "color_p1"].apply(
                lambda c: c[:3] + [20]
            )
            map_overlaps.loc[~is_match, "color_p2"] = map_overlaps.loc[~is_match, "color_p2"].apply(
                lambda c: c[:3] + [20]
            )

        map_overlaps["tip_title"] = "Matched Overlap - " + map_overlaps["Criticality"]
        map_overlaps["tip_sub"] = map_overlaps["Project 1"] + " ↔ " + map_overlaps["Project 2"]
        map_overlaps["tip_body"] = (
            "Distance: "
            + map_overlaps["Dist. (mi)"].astype(str)
            + " mi | Time Gap: "
            + map_overlaps["Gap (days)"].astype(str)
            + " days | Est. Savings: $"
            + map_overlaps["Savings ($)"].apply(lambda x: f"{x:,}")
        )

        overlap_arcs = pdk.Layer(
            "ArcLayer",
            data=map_overlaps,
            get_source_position=["p1_lon", "p1_lat"],
            get_target_position=["p2_lon", "p2_lat"],
            get_source_color="color_p1",
            get_target_color="color_p2",
            get_width="arc_width",
            width_min_pixels=1,
            width_max_pixels=4,
            pickable=True,
            auto_highlight=True,
        )
        layers.append(overlap_arcs)

    return layers


def render_map(projects_df, overlaps_df, selected_overlaps=None):
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
            <span style="font-size: 1.45rem; font-weight: 700; color: #ffffff;">
                Coordination Overlaps
            </span>
            <span style="background: #27272a; border: 1px solid #3f3f46; color: #e4e4e7; font-size: 0.8rem; font-weight: 600; padding: 2px 9px; border-radius: 9999px;">
                {len(overlaps_df)} Matches
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    unique_utils = list(projects_df["utility"].unique())
    color_lookup = {u: UTILITY_COLOR_PALETTE[i % len(UTILITY_COLOR_PALETTE)] for i, u in enumerate(unique_utils)}

    active_projects = set()
    if not overlaps_df.empty:
        active_projects = set(overlaps_df["Project 1"]).union(set(overlaps_df["Project 2"]))

    layers = build_map_layers(
        projects_df, overlaps_df, color_lookup, active_projects, selected_overlaps=selected_overlaps
    )

    # dynamic camera: zooms and centers based on the geographic spread of user selections
    if selected_overlaps is not None and not selected_overlaps.empty:
        all_lats = list(selected_overlaps["p1_lat"]) + list(selected_overlaps["p2_lat"])
        all_lons = list(selected_overlaps["p1_lon"]) + list(selected_overlaps["p2_lon"])

        view_lat = sum(all_lats) / len(all_lats)
        view_lon = sum(all_lons) / len(all_lons)

        # calculate bounding box spread in degrees to figure out how far to zoom out
        lat_span = max(all_lats) - min(all_lats)
        lon_span = max(all_lons) - min(all_lons)
        max_span = max(lat_span, lon_span)

        # step zoom levels based on how far apart the selected projects are
        if max_span < 0.6:
            view_zoom = 8.5
            view_pitch = 45
        elif max_span < 1.8:
            view_zoom = 7.4
            view_pitch = 40
        else:
            view_zoom = 6.6
            view_pitch = 35
    else:
        # fallback to viewing the entire dataset
        view_lat = projects_df["lat_center"].mean()
        view_lon = projects_df["lon_center"].mean()
        view_zoom = 6.5
        view_pitch = 35

    st.pydeck_chart(
        pdk.Deck(
            map_style="dark",
            initial_view_state=pdk.ViewState(
                latitude=view_lat,
                longitude=view_lon,
                zoom=view_zoom,
                pitch=view_pitch,
            ),
            layers=layers,
            tooltip={
                # type: ignore
                "html": "<b>{tip_title}</b><br/>{tip_sub}<br/>{tip_body}",
                "style": {
                    "backgroundColor": "#1e1e1e",
                    "color": "white",
                    "fontSize": "13px",
                    "maxWidth": "250px",
                },
            },
        )
    )

    legend_items = [
        f"<span style='display:inline-block;width:10px;height:10px;background-color:rgb({c[0]},{c[1]},{c[2]});border-radius:50%;margin-right:6px;'></span><b>{u}</b>"
        for u, c in color_lookup.items()
    ]
    st.markdown(
        "<div style='margin-top: -5px; margin-bottom: 1.5rem; font-size: 0.85rem; color: #888;'>"
        + " &nbsp;&nbsp;&bull;&nbsp;&nbsp; ".join(legend_items)
        + "</div>",
        unsafe_allow_html=True,
    )


def render_raw_data(projects_df):
    with st.expander("View Raw Projects Data"):
        utilities_str = ", ".join(sorted(projects_df["utility"].unique()))
        st.write(f"**Utilities represented:** {utilities_str}")

        col1, col2 = st.columns(2)
        col1.metric("Total Project Count", len(projects_df))
        col2.metric("Total Utility Count", len(projects_df["utility"].unique()))

        st.dataframe(
            projects_df[
                ["project_id", "utility", "state", "project_name", "lat_center", "lon_center", "in_service_date"]
            ],
            use_container_width=True,
            hide_index=True,
        )


# --- main ---
def main():
    inject_custom_css()
    render_title()

    projects_df = load_data()
    all_utilities = sorted(projects_df["utility"].unique())

    # render sidebar with dynamic filters
    max_dist, max_time_gap, selected_utils, selected_tiers = render_sidebar(all_utilities)

    # calculate overlaps based on distance and schedule sliders
    overlaps_df = find_overlaps(projects_df, max_dist, max_time_gap)

    # apply utility and tier filters
    if not overlaps_df.empty:
        # both utilities must be in selected utilities and tier must match selected tiers
        mask = (
            overlaps_df["Utility 1"].isin(selected_utils)
            & overlaps_df["Utility 2"].isin(selected_utils)
            & overlaps_df["Criticality"].isin(selected_tiers)
        )
        # wrap in dataframe so pyright preserves the dataframe type instead of inferring ndarray
        overlaps_df = pd.DataFrame(overlaps_df.loc[mask])

        if not overlaps_df.empty:
            # rank entries primarily by cost savings and then distance
            overlaps_df = overlaps_df.sort_values(
                by=["Savings ($)", "Dist. (mi)"], ascending=[False, True]
            ).reset_index(drop=True)
            overlaps_df.insert(0, "Rank", range(1, len(overlaps_df) + 1))

    # safely extract user's clicked rows from streamlit's session state dictionary
    selected_overlaps = None
    if "overlaps_table" in st.session_state:
        selected_rows = st.session_state.overlaps_table.get("selection", {}).get("rows", [])

        # verify the selected row indices actually exist in our current filtered dataframe
        if selected_rows and not overlaps_df.empty:
            valid_indices = [idx for idx in selected_rows if idx < len(overlaps_df)]
            if valid_indices:
                selected_overlaps = overlaps_df.iloc[valid_indices]

    render_map(projects_df, overlaps_df, selected_overlaps=selected_overlaps)

    if not overlaps_df.empty:
        st.dataframe(
            overlaps_df[
                [
                    "Rank",
                    "Criticality",
                    "Savings ($)",
                    "Dist. (mi)",
                    "Gap (days)",
                    "Project 1",
                    "Utility 1",
                    "Project 2",
                    "Utility 2",
                ]
            ],
            column_config={
                "Savings ($)": st.column_config.NumberColumn(
                    "Savings ($)",
                    format="$%d",
                ),
            },
            use_container_width=True,
            hide_index=True,
            key="overlaps_table",
            on_select="rerun",
            selection_mode="multi-row",
        )

        # export selected rows if active, otherwise export all filtered matches
        if selected_overlaps is not None and not selected_overlaps.empty:
            export_df = selected_overlaps
            btn_label = f"Export Selected Seams ({len(selected_overlaps)}) (CSV)"
            file_name = f"GridAlign_{len(selected_overlaps)}_Selected_Seams.csv"
        else:
            export_df = overlaps_df
            btn_label = f"Export Filtered Matches ({len(overlaps_df)}) (CSV)"
            file_name = f"GridAlign_All_{len(overlaps_df)}_Filtered_Seams.csv"

        # dataframe to csv
        csv_data = (
            export_df[
                [
                    "Rank",
                    "Criticality",
                    "Savings ($)",
                    "Dist. (mi)",
                    "Gap (days)",
                    "Project 1",
                    "Utility 1",
                    "Project 2",
                    "Utility 2",
                ]
            ]
            .to_csv(index=False)
            .encode("utf-8")
        )

        st.download_button(
            label=btn_label,
            data=csv_data,
            file_name=file_name,
            mime="text/csv",
        )
    else:
        st.info("No overlaps found within the selected thresholds. Try adjusting the sliders above.")

    st.divider()
    render_raw_data(projects_df)


if __name__ == "__main__":
    main()
