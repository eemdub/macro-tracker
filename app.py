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
# STREAKS
# ==========================================================

def calculate_food_streak(food_dates):
    if not food_dates:
        return 0
    dates = sorted(set(food_dates))
    streak = 0
    today = date.today()
    while True:
        check_date = str(today - timedelta(days=streak))
        if check_date in dates:
            streak += 1
        else:
            break
    return streak

def calculate_water_streak(df):
    if df.empty:
        return 0
    df = df.copy()
    df["date_only"] = df["date"].dt.date
    daily_totals = df.groupby("date_only")["water"].sum()
    streak = 0
    today = date.today()
    while True:
        check_date = today - timedelta(days=streak)
        if daily_totals.get(check_date, 0) >= WATER_GOAL:
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

foods_df = load_foods()
water_df = load_water()
weights_df = load_weights()

with top2:
    if st.button("Weekly Review"):
        st.info("Weekly analytics coming soon.")

with top3:
    st.markdown("### 🔥 Streaks")
    food_streak = calculate_food_streak(
        foods_df["date"].tolist() if not foods_df.empty else []
    )
    water_streak = calculate_water_streak(water_df)
    weight_streak = calculate_food_streak(
        weights_df["date"].dt.strftime("%Y-%m-%d").tolist()
        if not weights_df.empty else []
    )

    st.markdown(f"Food: {food_streak}")
    st.markdown(f"Water: {water_streak}")
    st.markdown(f"Weight: {weight_streak}")

# ==========================================================
# FOOD + MACROS
# ==========================================================

left, right = st.columns([1,1])
day_df = foods_df[foods_df["date"] == selected_date_str] if not foods_df.empty else pd.DataFrame()

with left:
    st.header("Add Food")

    entry_mode = st.radio("Entry Method", ["Search USDA","Manual Entry"], horizontal=True)

    # ------------------------------------------------------
    # USDA SEARCH
    # ------------------------------------------------------
    if entry_mode == "Search USDA":
        query = st.text_input("Search food")

        if st.button("Search"):
            response = requests.get(
                "https://api.nal.usda.gov/fdc/v1/foods/search",
                params={"query": query, "api_key": USDA_API_KEY, "pageSize":5}
            )
            if response.status_code == 200:
                st.session_state.search_results = response.json().get("foods", [])
            else:
                st.error("USDA API error.")

        if "search_results" in st.session_state:
            options = {f["description"]: f for f in st.session_state.search_results}
            selected = st.selectbox("Select food", list(options.keys()))
            food = options[selected]
            servings = st.number_input("Servings", 0.0, step=0.5)

            if st.button("Add Food"):
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

    # ------------------------------------------------------
    # MANUAL ENTRY (STRUCTURED)
    # ------------------------------------------------------
    else:

        col1, col2 = st.columns(2)

        with col1:
            protein = st.number_input("Protein (g)", 0.0)
            fat = st.number_input("Fat (g)", 0.0)
            fiber = st.number_input("Fiber (g)", 0.0)

        with col2:
            carbs = st.number_input("Carbs (g)", 0.0)
            sat = st.number_input("Saturated Fat (g)", 0.0)

        calories_per_serving = protein*4 + carbs*4 + fat*9
        st.markdown(f"**Calories (per serving): {round(calories_per_serving,1)} kcal**")

        servings = st.number_input("Total Servings", 1.0)
        name = st.text_input("Food name")

        if st.button("Add Manual Food"):
            daily_ws.append_row([
                str(uuid.uuid4()),
                selected_date_str,
                name,
                servings,
                calories_per_serving*servings,
                protein*servings,
                fat*servings,
                sat*servings,
                carbs*servings,
                fiber*servings
            ])
            load_foods.clear()
            st.rerun()

# ==========================================================
# MACRO VISUALIZATION (VERTICAL BAR WITH LABELS)
# ==========================================================

import altair as alt

with right:
    st.header("Daily Totals")

    if not day_df.empty:
        totals = day_df.sum(numeric_only=True)

        chart_data = []
        for k, goal in DAILY_GOALS.items():
            value = totals.get(k, 0)
            percent = value / goal if goal > 0 else 0

            chart_data.append({
                "Macro": k.capitalize(),
                "Percent": percent,
                "Display": f"{round(value,1)} / {goal}"
            })

        chart_df = pd.DataFrame(chart_data)

        # Base bar chart
        bars = alt.Chart(chart_df).mark_bar().encode(
            x=alt.X("Macro:N", sort=None),
            y=alt.Y("Percent:Q", scale=alt.Scale(domain=[0, 1.5])),
        )

        # Value labels above bars
        text = alt.Chart(chart_df).mark_text(
            dy=-5
        ).encode(
            x="Macro:N",
            y="Percent:Q",
            text="Display:N"
        )

        chart = bars + text

        st.altair_chart(chart, use_container_width=True)

    else:
        st.info("No food logged for this day.")

# ==========================================================
# WATER & WEIGHT (2x2)
# ==========================================================

st.divider()
st.header("Water & Weight")

input_col1, input_col2 = st.columns(2)

with input_col1:
    st.subheader("Water Intake")
    water_amount = st.number_input("Add water (oz)", 0.0, step=4.0)

    if st.button("Add Water"):
        records = water_ws.get_all_records()
        updated = False
        for i, row in enumerate(records, start=2):
            if row["date"] == selected_date_str:
                new_total = float(row["water"]) + water_amount
                water_ws.update_cell(i, 2, new_total)
                updated = True
                break
        if not updated:
            water_ws.append_row([selected_date_str, water_amount])
        load_water.clear()
        st.rerun()

with input_col2:
    st.subheader("Weight")
    weight_input = st.number_input("Enter weight", 0.0, step=0.1)

    if st.button("Save Weight"):
        records = weight_ws.get_all_records()
        updated = False
        for i, row in enumerate(records, start=2):
            if row["date"] == selected_date_str:
                weight_ws.update_cell(i, 2, weight_input)
                updated = True
                break
        if not updated:
            weight_ws.append_row([selected_date_str, weight_input])
        load_weights.clear()
        st.rerun()

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("7 Day Water")
    water_df = load_water()
    if not water_df.empty:
        last7 = water_df[
            water_df["date"] >= pd.to_datetime(selected_date) - timedelta(days=6)
        ]
        if not last7.empty:
            last7 = last7.sort_values("date")
            st.line_chart(last7.set_index("date")["water"])

with chart_col2:
    st.subheader("Weight Trend")
    weights_df = load_weights()
    if not weights_df.empty:
        weights_df = weights_df.sort_values("date")
        weights_df["rolling_avg"] = weights_df["weight"].rolling(7).mean()
        st.line_chart(
            weights_df.set_index("date")[["weight","rolling_avg"]]
        )

# ==========================================================
# NOTES
# ==========================================================

st.divider()
st.header("Daily Notes")

notes_df = load_notes()
existing_note = ""

if not notes_df.empty:
    row = notes_df[notes_df["date"]==selected_date_str]
    if not row.empty:
        existing_note = row["notes"].iloc[0]

note_text = st.text_area("Notes", value=existing_note, height=200)

if st.button("Save Note"):
    records = notes_ws.get_all_records()
    updated = False
    for i, row in enumerate(records, start=2):
        if row["date"] == selected_date_str:
            notes_ws.update_cell(i, 2, note_text)
            updated = True
            break
    if not updated:
        notes_ws.append_row([selected_date_str, note_text])
    load_notes.clear()
    st.success("Note saved.")

