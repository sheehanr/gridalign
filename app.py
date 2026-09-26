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


col1, col2 = st.columns(2)
col1.metric("Total Projects", len(df))
col2.metric("Utilities Found", ", ".join(df["utility"].unique()))

st.subheader("Raw Projects Data")
st.dataframe(df[["project_id", "utility", "state", "project_name", "lat_center", "lon_center", "in_service_date"]])
