import streamlit as st
import pandas as pd
import requests
import uuid
import altair as alt
from datetime import date, timedelta
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

gc = gspread.authorize(creds)

sheet = gc.open_by_key(
    st.secrets["gcp_service_account"]["sheet_id"]
)

daily_ws = sheet.worksheet("Daily Foods")
saved_ws = sheet.worksheet("Saved Foods")
water_ws = sheet.worksheet("Water")
weight_ws = sheet.worksheet("Weights")
notes_ws = sheet.worksheet("Notes")

DAILY_GOALS = {
    "calories": 2000,
    "protein": 130,
    "fat": 70,
    "carbs": 130,
    "sat_fat": 15,
    "fiber": 25
}

# ==========================================================
# LOADERS
# ==========================================================

@st.cache_data(ttl=60)
def load_foods():
    df = pd.DataFrame(daily_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = df["date"].astype(str)
    numeric_cols = ["servings","calories","protein","fat","sat_fat","carbs","fiber"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

@st.cache_data(ttl=60)
def load_water():
    df = pd.DataFrame(water_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["water"] = pd.to_numeric(df["water"], errors="coerce")
    return df.dropna()

@st.cache_data(ttl=60)
def load_weights():
    df = pd.DataFrame(weight_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    return df.dropna()

@st.cache_data(ttl=60)
def load_notes():
    df = pd.DataFrame(notes_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = df["date"].astype(str)
    return df

# ==========================================================
# STREAK FUNCTION
# ==========================================================

def calculate_streak(df):
    if df.empty:
        return 0, 0

    dates = pd.to_datetime(df["date"]).dt.date.unique()
    dates = sorted(dates)

    longest = 0
    current = 0
    streak = 0
    prev = None

    for d in dates:
        if prev is None or (d - prev).days == 1:
            streak += 1
        else:
            streak = 1
        longest = max(longest, streak)
        prev = d

    if dates and (date.today() - dates[-1]).days <= 1:
        current = streak

    return current, longest

# ==========================================================
# TOP ROW
# ==========================================================

col1, col2, col3 = st.columns([1,1,1])

with col1:
    selected_date = st.date_input("Select Date", date.today())
    selected_date_str = str(selected_date)

foods_df = load_foods()
water_df = load_water()
weights_df = load_weights()

with col3:
    st.markdown("### 🔥 Streaks")
    current, longest = calculate_streak(foods_df)
    st.metric("Current", current)
    st.metric("Longest", longest)

# ==========================================================
# DAILY TOTALS WITH PROGRESS
# ==========================================================

st.divider()
st.header("Daily Totals")

day_df = foods_df[foods_df["date"] == selected_date_str] if not foods_df.empty else pd.DataFrame()

if not day_df.empty:
    totals = day_df.sum(numeric_only=True)
    for k, goal in DAILY_GOALS.items():
        value = totals.get(k, 0)
        percent = min(value/goal, 1.0)
        st.write(f"**{k.capitalize()}**: {round(value,1)} / {goal}")
        st.progress(percent)

# ==========================================================
# WEEKLY CALORIE TREND
# ==========================================================

st.divider()
st.header("7 Day Calorie Trend")

if not foods_df.empty:
    foods_df["date_dt"] = pd.to_datetime(foods_df["date"])
    last7 = foods_df[foods_df["date_dt"] >= pd.Timestamp.today() - pd.Timedelta(days=6)]
    weekly = last7.groupby("date_dt")["calories"].sum().reset_index()

    if not weekly.empty:
        chart = alt.Chart(weekly).mark_line(point=True).encode(
            x="date_dt:T",
            y="calories:Q"
        )
        st.altair_chart(chart, use_container_width=True)

# ==========================================================
# WATER & WEIGHT REDESIGN
# ==========================================================

st.divider()
st.header("Water & Weight")

input_col1, input_col2 = st.columns(2)

with input_col1:
    water_amount = st.number_input("Add water (oz)", 0.0, step=4.0)
    if st.button("Add Water"):
        water_ws.append_row([selected_date_str, water_amount])
        load_water.clear()
        st.rerun()

with input_col2:
    weight_input = st.number_input("Enter weight", 0.0, step=0.1)
    if st.button("Save Weight"):
        weight_ws.append_row([selected_date_str, weight_input])
        load_weights.clear()
        st.rerun()

chart_col1, chart_col2 = st.columns(2)

start_date = pd.to_datetime(selected_date) - timedelta(days=6)

with chart_col1:
    if not water_df.empty:
        water_last7 = water_df[water_df["date"] >= start_date].copy()
        if not water_last7.empty:
            water_chart = alt.Chart(water_last7).mark_line(point=True).encode(
                x="date:T",
                y="water:Q"
            )
            st.altair_chart(water_chart, use_container_width=True)

with chart_col2:
    if not weights_df.empty:
        weight_last7 = weights_df[weights_df["date"] >= start_date].copy()
        if not weight_last7.empty:
            weight_chart = alt.Chart(weight_last7).mark_line(point=True).encode(
                x="date:T",
                y=alt.Y("weight:Q", scale=alt.Scale(zero=False))
            )
            st.altair_chart(weight_chart, use_container_width=True)

# ==========================================================
# NOTES FIXED
# ==========================================================

st.divider()
st.header("Daily Notes")

notes_df = load_notes()
existing_note = ""

if not notes_df.empty:
    row = notes_df[notes_df["date"]==selected_date_str]
    if not row.empty:
        existing_note = row["notes"].iloc[-1]

note_text = st.text_area("Notes", value=existing_note, height=200)

if st.button("Save Note"):
    records = notes_ws.get_all_records()
    updated = False
    for i, r in enumerate(records, start=2):
        if r["date"] == selected_date_str:
            notes_ws.update_cell(i, 2, note_text)
            updated = True
            break
    if not updated:
        notes_ws.append_row([selected_date_str, note_text])

    load_notes.clear()
    st.success("Saved")
    st.rerun()

