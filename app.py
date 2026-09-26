from math import asin, cos, radians, sin, sqrt

import pandas as pd
import streamlit as st

st.set_page_config(layout="wide", page_title="GridLock Coordinator")
st.title("GridLock Coordinator")


# Load projects sheet and keep loaded
@st.cache_data
def load_data():
    path = "Sperry-Tech-Challenge/Projects_Overlaps.xlsx"
    df = pd.read_excel(path, sheet_name="projects")
    df["in_service_date"] = pd.to_datetime(df["in_service_date"])
    return df


df = load_data()


def haversine(lat1, lon1, lat2, lon2):
    # R = 6371.0  # Earth radius in km
    R = 3959.0  # Earth radius in mi
    lat_diff = radians(lat2 - lat1)
    lon_diff = radians(lon2 - lon1)
    a = sin(lat_diff / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_diff / 2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


col1, col2 = st.columns(2)
col1.metric("Total Projects", len(df))
col2.metric("Utilities Found", ", ".join(df["utility"].unique()))

st.subheader("Raw Projects Data")
st.dataframe(df[["project_id", "utility", "state", "project_name", "lat_center", "lon_center", "in_service_date"]])
