import pydeck as pdk
import streamlit as st

from constants import UTILITY_COLOR_PALETTE


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

            /* center metric cards, labels, and values */
            [data-testid="stMetric"] {
                display: flex !important;
                flex-direction: column !important;
                align-items: center !important;
                justify-content: center !important;
                text-align: center !important;
            }

            [data-testid="stMetricLabel"] {
                display: flex !important;
                justify-content: center !important;
                width: 100% !important;
            }

            [data-testid="stMetricValue"] {
                display: flex !important;
                justify-content: center !important;
                width: 100% !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_title():
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 3rem;">
            <div style="display: inline-flex; align-items: center; justify-content: center; gap: 16px; margin-bottom: 0;">
                <svg width="40" height="50" viewBox="0 0 34 42" fill="none" stroke="#f97316" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <!-- high voltage transmission tower -->
                    <line x1="17" y1="2" x2="6" y2="40"/>
                    <line x1="17" y1="2" x2="28" y2="40"/>
                    <line x1="3" y1="12" x2="31" y2="12"/>
                    <line x1="5" y1="22" x2="29" y2="22"/>
                    <line x1="8" y1="32" x2="26" y2="32"/>
                    <line x1="10" y1="12" x2="24" y2="22"/>
                    <line x1="24" y1="12" x2="10" y2="22"/>
                    <line x1="8" y1="22" x2="26" y2="32"/>
                    <line x1="26" y1="22" x2="8" y2="32"/>
                </svg>
                <h1 style="margin: 0; font-size: 3.25rem; font-weight: 800; letter-spacing: -0.03em; color: #f4f4f5; line-height: 1;">
                    GridAlign
                </h1>
            </div>
            <p style="margin: 0; font-size: 0.95rem; color: #71717a; font-weight: 500; letter-spacing: 0.01em;">
                Cross-Utility Transmission Coordination
            </p>
        </div>
        """,
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
    col_title, col_action = st.columns([8, 1], vertical_alignment="center")

    with col_title:
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 12px;">
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

    with col_action, st.popover("Upload", use_container_width=True):
        st.caption("Upload CSV or XLSX matching challenge data schema")
        st.file_uploader(
            "Upload Additional Data",
            type=["csv", "xlsx"],
            accept_multiple_files=True,
            key="dataset_upload",
            label_visibility="collapsed",
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
    with st.expander("View All Loaded Data"):
        utilities_str = ", ".join(sorted(projects_df["utility"].unique()))
        st.write(f"**Utilities represented:** {utilities_str}")

        col1, col2 = st.columns(2)
        col1.metric("Total Project Count", len(projects_df))
        col2.metric("Total Utility Count", len(projects_df["utility"].unique()))

        # safe column filter prevents KeyError if an uploaded file omits state or other fields
        display_cols = [
            "project_id",
            "utility",
            "state",
            "project_name",
            "lat_center",
            "lon_center",
            "in_service_date",
        ]
        safe_cols = [c for c in display_cols if c in projects_df.columns]

        st.dataframe(
            projects_df[safe_cols],
            use_container_width=True,
            hide_index=True,
        )
