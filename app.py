import streamlit as st
import pandas as pd
import requests
import uuid
from datetime import date, timedelta
import gspread
from google.oauth2.service_account import Credentials

# ==========================================================
# CONFIG
# ==========================================================

st.set_page_config(layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

gc = gspread.authorize(creds)
sheet = gc.open_by_key(st.secrets["gcp_service_account"]["sheet_id"])

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

WATER_GOAL = 75

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
def load_saved_foods():
    df = pd.DataFrame(saved_ws.get_all_records())
    if df.empty:
        return df
    numeric_cols = ["calories","protein","fat","sat_fat","carbs","fiber"]
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
    df = df[["date","weight"]]
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
# STREAKS
# ==========================================================

def calculate_streak(dates):
    if not dates:
        return 0
    dates = sorted(set(dates))
    streak = 0
    today = date.today()
    for i in range(len(dates)-1, -1, -1):
        if str(today - timedelta(days=streak)) == dates[i]:
            streak += 1
        else:
            break
    return streak

def calculate_water_streak(df):
    if df.empty:
        return 0
    df = df.sort_values("date")
    streak = 0
    today = date.today()
    for i in range(len(df)-1, -1, -1):
        if df.iloc[i]["water"] >= WATER_GOAL and df.iloc[i]["date"].date() == today - timedelta(days=streak):
            streak += 1
        else:
            break
    return streak

# ==========================================================
# TOP BAR
# ==========================================================

top1, top2, top3 = st.columns([1,1,1])

with top1:
    selected_date = st.date_input("Select Date", date.today())
    selected_date_str = str(selected_date)

with top2:
    if st.button("Weekly Review"):
        st.info("Weekly analytics coming soon.")

foods_df = load_foods()
water_df = load_water()
weights_df = load_weights()

with top3:
    st.markdown("### 🔥 Streaks")
    st.markdown(f"Food: {calculate_streak(foods_df['date'].tolist() if not foods_df.empty else [])}")
    st.markdown(f"Water: {calculate_water_streak(water_df)}")
    st.markdown(f"Weight: {calculate_streak(weights_df['date'].dt.strftime('%Y-%m-%d').tolist() if not weights_df.empty else [])}")

# ==========================================================
# FOOD + MACRO CHART
# ==========================================================

left, right = st.columns([1,1])
day_df = foods_df[foods_df["date"] == selected_date_str] if not foods_df.empty else pd.DataFrame()

with left:
    st.header("Add Food")

    entry_mode = st.radio("Entry Method", ["Search USDA","Manual / Saved"], horizontal=True)

    if entry_mode == "Search USDA":
        query = st.text_input("Search food")
        if st.button("Search USDA"):
            res = requests.get(
                "https://api.nal.usda.gov/fdc/v1/foods/search",
                params={"query": query, "api_key": USDA_API_KEY, "pageSize":5}
            ).json().get("foods", [])
            st.session_state.search_results = res

        if "search_results" in st.session_state:
            options = {f["description"]: f for f in st.session_state.search_results}
            selected = st.selectbox("Select food", list(options.keys()))
            food = options[selected]
            servings = st.number_input("Servings", 0.0, step=0.5)

            if st.button("Add USDA Food"):
                nutrients = food.get("foodNutrients", [])
                def get_val(id):
                    return next((n["value"] for n in nutrients if n["nutrientId"]==id),0)

                daily_ws.append_row([
                    str(uuid.uuid4()),
                    selected_date_str,
                    selected,
                    servings,
                    get_val(1008)*servings,
                    get_val(1003)*servings,
                    get_val(1004)*servings,
                    get_val(1258)*servings,
                    get_val(1005)*servings,
                    get_val(1079)*servings
                ])
                load_foods.clear()
                st.rerun()

    else:
        saved_df = load_saved_foods()

        search_term = st.text_input("Search Saved Foods")
        filtered = saved_df[
            saved_df["food"].str.contains(search_term, case=False, na=False)
        ] if search_term and not saved_df.empty else saved_df

        options = ["New Food"] + filtered["food"].tolist() if not saved_df.empty else ["New Food"]
        selection = st.selectbox("Choose Food", options)

        if selection != "New Food":
            row = saved_df[saved_df["food"]==selection].iloc[0]
            servings = st.number_input("Servings", 1.0)

            if st.button("Add Saved Food"):
                daily_ws.append_row([
                    str(uuid.uuid4()),
                    selected_date_str,
                    selection,
                    servings,
                    row["calories"]*servings,
                    row["protein"]*servings,
                    row["fat"]*servings,
                    row["sat_fat"]*servings,
                    row["carbs"]*servings,
                    row["fiber"]*servings
                ])
                load_foods.clear()
                st.rerun()

        else:
            name = st.text_input("Food name")
            protein = st.number_input("Protein (g)", 0.0)
            carbs = st.number_input("Carbs (g)", 0.0)
            fat = st.number_input("Fat (g)", 0.0)
            fiber = st.number_input("Fiber (g)", 0.0)
            sat = st.number_input("Sat Fat (g)", 0.0)
            servings = st.number_input("Servings", 1.0)

            calories = (protein*4 + carbs*4 + fat*9)

            if st.button("Add Manual Food"):
                daily_ws.append_row([
                    str(uuid.uuid4()),
                    selected_date_str,
                    name,
                    servings,
                    calories*servings,
                    protein*servings,
                    fat*servings,
                    sat*servings,
                    carbs*servings,
                    fiber*servings
                ])

                if name and name not in saved_df["food"].tolist():
                    saved_ws.append_row([name, calories, protein, fat, sat, carbs, fiber])
                    load_saved_foods.clear()

                load_foods.clear()
                st.rerun()

# ================= MACRO CHART =================
with right:
    st.header("Daily Totals")

    if not day_df.empty:
        totals = day_df.sum(numeric_only=True)

        labels = []
        values = []

        for k in DAILY_GOALS:
            remaining = DAILY_GOALS[k] - totals.get(k,0)
            labels.append(f"{k}\n{round(remaining,1)} left")
            values.append(min(totals.get(k,0)/DAILY_GOALS[k],1.5))

        chart_df = pd.DataFrame({"Percent":values}, index=labels)
        st.bar_chart(chart_df)

# ==========================================================
# WATER + WEIGHT (COMBINED CHART ROW)
# ==========================================================

import altair as alt

row_left, row_right = st.columns([1,2])

# ---------------- LEFT SIDE (STACKED INPUTS) ----------------
with row_left:
    st.header("Water & Weight")

    # -------- WATER INPUT --------
    water_amount = st.number_input("Add water (oz)", 0.0, step=4.0)

    if st.button("Add Water"):
        existing = water_df[water_df["date"]==pd.to_datetime(selected_date)]
        if existing.empty:
            water_ws.append_row([selected_date_str, water_amount])
        else:
            row_index = existing.index[0] + 2
            water_ws.update_cell(row_index,2,float(existing["water"].iloc[0]) + water_amount)
        load_water.clear()
        st.rerun()

    st.divider()

    # -------- WEIGHT INPUT --------
    weight_input = st.number_input("Enter weight", 0.0, step=0.1)

    if st.button("Save Weight"):
        existing = weights_df[weights_df["date"]==pd.to_datetime(selected_date)]
        if existing.empty:
            weight_ws.append_row([selected_date_str, weight_input])
        else:
            row_index = existing.index[0] + 2
            weight_ws.update_cell(row_index,2,weight_input)
        load_weights.clear()
        st.rerun()

# ==========================================================
# 7 DAY WATER & WEIGHT COMBINED CHART
# ==========================================================

import altair as alt

with row_right:
    st.header("7 Day Water & Weight")

    water_df = load_water()
    weights_df = load_weights()

    if not water_df.empty or not weights_df.empty:

        start_date = pd.to_datetime(selected_date) - timedelta(days=6)

        water_last7 = water_df[water_df["date"] >= start_date][["date","water"]]
        weight_last7 = weights_df[weights_df["date"] >= start_date][["date","weight"]]

        # Ensure datetime format
        water_last7["date"] = pd.to_datetime(water_last7["date"])
        weight_last7["date"] = pd.to_datetime(weight_last7["date"])

        combined = pd.merge(
            water_last7,
            weight_last7,
            on="date",
            how="outer"
        ).sort_values("date")

        # Drop rows where both values missing
        combined = combined.dropna(how="all", subset=["water","weight"])

        if not combined.empty:

            # Remove time portion (prevents AM/PM display)
            combined["date"] = pd.to_datetime(combined["date"]).dt.date

            base = alt.Chart(combined).encode(
                x=alt.X(
                    "date:T",
                    title="Date",
                    axis=alt.Axis(format="%b %d")
                )
            )

            # Water line
            water_line = base.mark_line(
                color="#1f77b4",
                strokeWidth=4,
                point=True
            ).encode(
                y=alt.Y(
                    "water:Q",
                    title="Water (oz)"
                ),
                tooltip=["date:T", "water:Q"]
            )

            # Weight line (fixed axis 300–400)
            weight_line = base.mark_line(
                color="#d62728",
                strokeWidth=4,
                point=True
            ).encode(
                y=alt.Y(
                    "weight:Q",
                    title="Weight",
                    scale=alt.Scale(domain=[300, 400]),
                    axis=alt.Axis(titleColor="#d62728")
                ),
                tooltip=["date:T", "weight:Q"]
            )

            chart = alt.layer(
                water_line,
                weight_line
            ).resolve_scale(
                y="independent"
            )

            st.altair_chart(chart, use_container_width=True)

        else:
            st.info("No data available for last 7 days.")

# ==========================================================
# NOTES (FULL ROW)
# ==========================================================

st.divider()
st.header("Daily Notes")

notes_df = load_notes()

existing_note = ""
if not notes_df.empty:
    row = notes_df[notes_df["date"]==selected_date_str]
    if not row.empty:
        existing_note = row["notes"].iloc[0]

note_text = st.text_area("Notes", value=existing_note, height=180)

# ==========================================================
# SAVE NOTE + END DAY ROW
# ==========================================================

button_left, button_right = st.columns([1,1])

with button_left:
    if st.button("Save Note"):
        if notes_df.empty or selected_date_str not in notes_df["date"].values:
            notes_ws.append_row([selected_date_str, note_text])
        else:
            row_index = notes_df.index[
                notes_df["date"]==selected_date_str
            ][0] + 2
            notes_ws.update_cell(row_index,2,note_text)
        load_notes.clear()
        st.success("Note saved.")

with button_right:
    if st.button("End Day"):
        st.success("Day complete.")










