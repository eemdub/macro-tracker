import streamlit as st
import pandas as pd
import requests
import uuid
from datetime import date, datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

# =============================
# CONFIG
# =============================

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

DAILY_GOALS = {
    "calories": 2000,
    "protein": 130,
    "fat": 70,
    "carbs": 130,
    "sat_fat": 15,
    "fiber": 25
}

WATER_GOAL = 75

# =============================
# LOADERS
# =============================

@st.cache_data(ttl=60)
def load_foods():
    df = pd.DataFrame(daily_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = df["date"].astype(str)
    return df

@st.cache_data(ttl=60)
def load_water():
    df = pd.DataFrame(water_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["water"] = pd.to_numeric(df["water"], errors="coerce")
    return df

@st.cache_data(ttl=60)
def load_weights():
    df = pd.DataFrame(weight_ws.get_all_records())
    if df.empty:
        return df
    df = df[["date","weight"]]
    df["date"] = pd.to_datetime(df["date"])
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    return df.dropna()

# =============================
# STREAK CALCULATIONS
# =============================

def calculate_food_streak(df):
    if df.empty:
        return 0
    dates = sorted(set(df["date"]))
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

def calculate_weight_streak(df):
    if df.empty:
        return 0
    df = df.sort_values("date")
    streak = 0
    today = date.today()
    for i in range(len(df)-1, -1, -1):
        if df.iloc[i]["date"].date() == today - timedelta(days=streak):
            streak += 1
        else:
            break
    return streak

# =============================
# TOP BAR LAYOUT
# =============================

top1, top2, top3 = st.columns([1,1,1])

with top1:
    selected_date = st.date_input("Select Date", date.today())
    selected_date_str = str(selected_date)

with top2:
    if st.button("Weekly Review"):
        st.info("Weekly review coming soon.")

with top3:
    foods_df = load_foods()
    water_df = load_water()
    weights_df = load_weights()

    st.markdown("### 🔥 Streaks")
    st.markdown(f"Food: {calculate_food_streak(foods_df)} days")
    st.markdown(f"Water: {calculate_water_streak(water_df)} days")
    st.markdown(f"Weight: {calculate_weight_streak(weights_df)} days")

# ==========================================================
# FOOD ENTRY + MACRO CHART
# ==========================================================

left, right = st.columns([1,1])

day_df = foods_df[foods_df["date"] == selected_date_str] if not foods_df.empty else pd.DataFrame()

with left:
    st.header("Add Food")

    entry_mode = st.radio(
        "Entry Method",
        ["Search USDA","Enter Manually"],
        horizontal=True
    )

    if entry_mode == "Search USDA":
        food_query = st.text_input("Search food")
        if st.button("Search"):
            results = requests.get(
                "https://api.nal.usda.gov/fdc/v1/foods/search",
                params={"query": food_query, "api_key": USDA_API_KEY, "pageSize":5}
            ).json().get("foods")
            st.session_state.search_results = results

        if "search_results" in st.session_state:
            options = {f["description"]: f for f in st.session_state.search_results}
            selected = st.selectbox("Select food", list(options.keys()))
            food = options[selected]

            servings = st.number_input("Servings", 0.0, step=0.5)

            if st.button("Add"):
                nutrients = food.get("foodNutrients", [])
                fiber = next((n["value"] for n in nutrients if n["nutrientId"]==1079),0)
                calories = next((n["value"] for n in nutrients if n["nutrientId"]==1008),0)
                protein = next((n["value"] for n in nutrients if n["nutrientId"]==1003),0)
                fat = next((n["value"] for n in nutrients if n["nutrientId"]==1004),0)
                carbs = next((n["value"] for n in nutrients if n["nutrientId"]==1005),0)
                sat = next((n["value"] for n in nutrients if n["nutrientId"]==1258),0)

                daily_ws.append_row([
                    str(uuid.uuid4()),
                    selected_date_str,
                    food["description"],
                    servings,
                    calories*servings,
                    protein*servings,
                    fat*servings,
                    sat*servings,
                    carbs*servings,
                    fiber*servings
                ])
                load_foods.clear()
                st.rerun()

    else:
        name = st.text_input("Food name")
        protein = st.number_input("Protein", 0.0)
        carbs = st.number_input("Carbs", 0.0)
        fat = st.number_input("Fat", 0.0)
        fiber = st.number_input("Fiber", 0.0)
        sat = st.number_input("Sat Fat", 0.0)
        servings = st.number_input("Servings", 1.0)

        calories = (protein*4 + carbs*4 + fat*9)*servings

        if st.button("Add Manual Food"):
            daily_ws.append_row([
                str(uuid.uuid4()),
                selected_date_str,
                name,
                servings,
                calories,
                protein*servings,
                fat*servings,
                sat*servings,
                carbs*servings,
                fiber*servings
            ])
            load_foods.clear()
            st.rerun()

with right:
    st.header("Daily Totals")

    if not day_df.empty:
        totals = day_df.sum(numeric_only=True)

        labels = []
        values = []

        for k in DAILY_GOALS:
            remaining = DAILY_GOALS[k] - totals.get(k,0)
            labels.append(f"{k}\n{round(remaining,1)} left")
            values.append(totals.get(k,0) / DAILY_GOALS[k])

        chart_df = pd.DataFrame({"Percent":values}, index=labels)
        st.bar_chart(chart_df)

# ==========================================================
# WATER ROW
# ==========================================================

water_left, water_right = st.columns([1,1])

with water_left:
    st.header("Water")

    add_water = st.number_input("Add water (oz)", 0.0, step=4.0)

    if st.button("Add Water"):
        today = str(selected_date)
        existing = water_df[water_df["date"]==pd.to_datetime(today)]
        if existing.empty:
            water_ws.append_row([today, add_water])
        else:
            idx = existing.index[0] + 2
            water_ws.update_cell(idx,2,float(existing["water"].iloc[0]) + add_water)
        load_water.clear()
        st.rerun()

with water_right:
    st.header("7 Day Water")

    if not water_df.empty:
        last_7 = water_df[water_df["date"] >= pd.to_datetime(selected_date)-timedelta(days=6)]
        st.line_chart(last_7.set_index("date")["water"])
