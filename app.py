import pandas as pd
import streamlit as st

from components import (
    inject_custom_css,
    render_map,
    render_raw_data,
    render_sidebar,
    render_title,
)
from logic import find_overlaps, get_combined_datasets

st.set_page_config(layout="wide", page_title="GridAlign", page_icon="⚡", initial_sidebar_state="expanded")


# --- main ---
def main():
    inject_custom_css()
    render_title()

    uploaded_files = st.session_state.get("dataset_upload", [])
    projects_df = get_combined_datasets(uploaded_files)

    all_utilities = sorted(projects_df["utility"].unique())

    # render sidebar with dynamic filters
    max_dist, max_time_gap, selected_utils, selected_tiers = render_sidebar(all_utilities)

    # calculate overlaps and multi-cluster regional hubs
    overlaps_df, hub_summary = find_overlaps(projects_df, max_dist, max_time_gap)

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

    hubs_df = pd.DataFrame()
    if not overlaps_df.empty:
        active_hub_names = set(overlaps_df["Hub"])
        hubs_data = []
        for name, h in hub_summary.items():
            if name in active_hub_names:
                hubs_data.append(
                    {
                        "Hub": name,
                        "Hub Savings ($)": h["hub_savings"],
                        "Project Count": h["project_count"],
                        "Projects": ", ".join(sorted(h["projects"])),
                    }
                )

        if hubs_data:
            hubs_df = pd.DataFrame(hubs_data).sort_values(by="Hub Savings ($)", ascending=False).reset_index(drop=True)
            hubs_df.insert(0, "Rank", range(1, len(hubs_df) + 1))

    # safely extract user's clicked rows, prioritizing direct hub clicks over individual lines
    selected_overlaps = None
    if "hubs_table" in st.session_state:
        selected_hub_rows = st.session_state.hubs_table.get("selection", {}).get("rows", [])
        if selected_hub_rows and not hubs_df.empty:
            valid_hub_indices = [idx for idx in selected_hub_rows if idx < len(hubs_df)]
            if valid_hub_indices:
                selected_hubs_names = hubs_df.iloc[valid_hub_indices]["Hub"].tolist()
                selected_overlaps = pd.DataFrame(overlaps_df[overlaps_df["Hub"].isin(selected_hubs_names)])

    if selected_overlaps is None and "overlaps_table" in st.session_state:
        selected_rows = st.session_state.overlaps_table.get("selection", {}).get("rows", [])
        if selected_rows and not overlaps_df.empty:
            valid_indices = [idx for idx in selected_rows if idx < len(overlaps_df)]
            if valid_indices:
                selected_overlaps = pd.DataFrame(overlaps_df.iloc[valid_indices])

    # render multi-cluster hub kpi metrics
    if not overlaps_df.empty:
        # count unique physical projects participating in any overlap
        unique_projects_count = len(set(overlaps_df["Project 1"]).union(set(overlaps_df["Project 2"])))
        active_hubs = overlaps_df["Hub"].nunique()
        total_hub_savings = sum(h["hub_savings"] for name, h in hub_summary.items() if name in set(overlaps_df["Hub"]))

        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric("Identified Hubs", f"{active_hubs}")
        col_kpi2.metric("Involved Projects", f"{unique_projects_count}")
        col_kpi3.metric("Potential Cost Savings", f"${total_hub_savings:,.0f}")
        st.write("")

    render_map(projects_df, overlaps_df, selected_overlaps=selected_overlaps)

    if not overlaps_df.empty:
        st.write("")
        st.write("##### Shared Staging Hubs")

        if not hubs_df.empty:
            st.dataframe(
                hubs_df,
                column_config={
                    "Hub Savings ($)": st.column_config.NumberColumn(
                        "Hub Savings ($)",
                        format="$%d",
                    ),
                },
                use_container_width=True,
                hide_index=True,
                key="hubs_table",
                on_select="rerun",
                selection_mode="multi-row",
            )

            # check if there are specific hub rows selected to selectively export
            selected_hubs_to_export = None
            if "hubs_table" in st.session_state:
                sel_rows = st.session_state.hubs_table.get("selection", {}).get("rows", [])
                if sel_rows:
                    valid_idx = [idx for idx in sel_rows if idx < len(hubs_df)]
                    if valid_idx:
                        selected_hubs_to_export = pd.DataFrame(hubs_df.iloc[valid_idx])

            export_hubs_df = selected_hubs_to_export if selected_hubs_to_export is not None else hubs_df
            hub_btn_label = f"Export {'Selected' if selected_hubs_to_export is not None else 'All'} Hubs Summary ({len(export_hubs_df)}) (CSV)"
            hub_file_name = f"GridAlign_{len(export_hubs_df)}_{'Selected' if selected_hubs_to_export is not None else 'All'}_Hubs_Summary.csv"

            hub_csv_data = export_hubs_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=hub_btn_label,
                data=hub_csv_data,
                file_name=hub_file_name,
                mime="text/csv",
                key="download_hubs_csv",
            )

        st.write("##### Overlapping Project Pairs")
        st.dataframe(
            overlaps_df[
                [
                    "Rank",
                    "Hub",
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
                    "Hub",
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
