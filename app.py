import streamlit as st
import pandas as pd
import altair as alt
import uuid
from datetime import date, timedelta
import gspread
from google.oauth2.service_account import Credentials

# ==========================================================
# CONFIG
# ==========================================================

st.set_page_config(layout="wide")

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

gc = gspread.authorize(creds)
sheet = gc.open_by_key(st.secrets["gcp_service_account"]["sheet_id"])

water_ws = sheet.worksheet("Water")
weight_ws = sheet.worksheet("Weights")
notes_ws = sheet.worksheet("Notes")

# ==========================================================
# HELPERS
# ==========================================================

def load_water():
    df = pd.DataFrame(water_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["water"] = pd.to_numeric(df["water"], errors="coerce")
    return df.dropna()

def load_weight():
    df = pd.DataFrame(weight_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    return df.dropna()

def load_notes():
    df = pd.DataFrame(notes_ws.get_all_records())
    if df.empty:
        return df
    return df

# ==========================================================
# TOP
# ==========================================================

selected_date = st.date_input("Select Date", date.today())
selected_date_str = str(selected_date)

st.divider()

# ==========================================================
# WATER + WEIGHT ROW
# ==========================================================

left_col, right_col = st.columns([1,2])

# ---------------- LEFT SIDE ----------------
with left_col:
    st.header("Water & Weight")

    water_amount = st.number_input("Add water (oz)", 0.0, step=4.0)
    if st.button("Add Water"):
        water_ws.append_row([selected_date_str, water_amount])
        st.rerun()

    st.divider()

    weight_input = st.number_input("Enter weight", 0.0, step=0.1)
    if st.button("Save Weight"):
        weight_ws.append_row([selected_date_str, weight_input])
        st.rerun()

# ---------------- RIGHT SIDE (CHART) ----------------
with right_col:
    st.header("7 Day Water & Weight")

    water_df = load_water()
    weight_df = load_weight()

    start_date = pd.to_datetime(selected_date) - timedelta(days=6)

    water_last7 = water_df[water_df["date"] >= start_date].copy() if not water_df.empty else pd.DataFrame()
    weight_last7 = weight_df[weight_df["date"] >= start_date].copy() if not weight_df.empty else pd.DataFrame()

    layers = []

    # -------- WATER --------
    if not water_last7.empty:
        water_last7["date"] = water_last7["date"].dt.date

        water_line = alt.Chart(water_last7).mark_line(
            strokeWidth=4,
            color="blue"
        ).encode(
            x=alt.X("date:T", axis=alt.Axis(format="%b %d")),
            y=alt.Y(
                "water:Q",
                scale=alt.Scale(domain=[0, 80]),
                axis=alt.Axis(title="Water (oz)", orient="left")
            )
        )

        water_points = alt.Chart(water_last7).mark_point(
            size=200,
            color="blue"
        ).encode(
            x="date:T",
            y="water:Q"
        )

        layers.extend([water_line, water_points])

    # -------- WEIGHT --------
    if not weight_last7.empty:
        weight_last7["date"] = weight_last7["date"].dt.date

        weight_line = alt.Chart(weight_last7).mark_line(
            strokeWidth=4,
            color="green"
        ).encode(
            x="date:T",
            y=alt.Y(
                "weight:Q",
                scale=alt.Scale(domain=[300, 400]),
                axis=alt.Axis(title="Weight (lbs)", orient="right")
            )
        )

        weight_points = alt.Chart(weight_last7).mark_point(
            size=200,
            color="green"
        ).encode(
            x="date:T",
            y="weight:Q"
        )

        layers.extend([weight_line, weight_points])

    if layers:
        chart = alt.layer(*layers).resolve_scale(y="independent")
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No data available for last 7 days.")

# ==========================================================
# NOTES ROW
# ==========================================================

st.divider()
st.header("Daily Notes")

notes_df = load_notes()

existing_note = ""
if not notes_df.empty:
    match = notes_df[notes_df["date"] == selected_date_str]
    if not match.empty:
        existing_note = match["notes"].iloc[0]

note_text = st.text_area("Notes", value=existing_note, height=200)

colA, colB = st.columns(2)

with colA:
    if st.button("Save Note"):
        notes_ws.append_row([selected_date_str, note_text])
        st.success("Note saved.")

with colB:
    if st.button("End Day"):
        st.success("Day Complete")
