import streamlit as st
import requests
import pandas as pd
from datetime import date
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
worksheet = sheet.sheet1

DAILY_GOALS = {
    "calories": 1800,
    "protein": 120,
    "fat": 60,
    "carbs": 180
}

# =============================
# SESSION STATE
# =============================

if "daily_log" not in st.session_state:
    st.session_state.daily_log = []

if "current_food" not in st.session_state:
    st.session_state.current_food = None

# =============================
# HELPERS
# =============================

def search_food(food_name):
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "query": food_name,
        "api_key": USDA_API_KEY,
        "pageSize": 5
    }
    response = requests.get(url, params=params)
    data = response.json()
    if not data.get("foods"):
        return None
    return data["foods"]


def extract_macros(food):
    nutrients = food.get("foodNutrients", [])

    macros = {
        "calories": 0,
        "protein": 0,
        "fat": 0,
        "carbs": 0
    }

    for n in nutrients:
        if n["nutrientId"] == 1008:
            macros["calories"] = n["value"]
        elif n["nutrientId"] == 1003:
            macros["protein"] = n["value"]
        elif n["nutrientId"] == 1004:
            macros["fat"] = n["value"]
        elif n["nutrientId"] == 1005:
            macros["carbs"] = n["value"]

    return macros


def append_to_sheet(df):
    rows = df.values.tolist()
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")

# =============================
# UI
# =============================

st.title("Daily Macro Tracker")

st.header("Add Food")

entry_mode = st.radio(
    "Select Entry Method:",
    ["Search USDA", "Enter Macros Manually"]
)

# =============================
# USDA MODE
# =============================

if entry_mode == "Search USDA":

    col1, col2 = st.columns([5, 1])

    with col1:
        food_query = st.text_input("Enter food name")

    with col2:
        search_clicked = st.button("Search")

    if search_clicked:
        results = search_food(food_query)
        if results:
            st.session_state.search_results = results
        else:
            st.error("No foods found.")
# =============================
# MANUAL MODE
# =============================

if entry_mode == "Enter Macros Manually":

    st.subheader("Manual Macro Entry")

    manual_name = st.text_input("Food name")

    col1, col2 = st.columns(2)

    with col1:
        manual_protein = st.number_input("Protein (g)", min_value=0.0)
        manual_fat = st.number_input("Fat (g)", min_value=0.0)

    with col2:
        manual_carbs = st.number_input("Carbs (g)", min_value=0.0)

    calculated_calories = (
        manual_protein * 4 +
        manual_carbs * 4 +
        manual_fat * 9
    )

    st.write(f"Calculated Calories: {round(calculated_calories,1)}")

    if st.button("Add Manual Entry"):

        entry = {
            "date": str(date.today()),
            "food": manual_name,
            "calories": calculated_calories,
            "protein": manual_protein,
            "fat": manual_fat,
            "carbs": manual_carbs
        }

        st.session_state.daily_log.append(entry)
        st.success("Manual entry added.")

# =============================
# TODAY'S LOG + DELETE
# =============================

st.header("Today's Log")

df = pd.DataFrame(st.session_state.daily_log)

if not df.empty:

    for i, row in df.iterrows():

        col1, col2 = st.columns([6, 1])

        with col1:
            st.write(
                f"{row['food']} | "
                f"{round(row['calories'],1)} cal | "
                f"P: {round(row['protein'],1)}g | "
                f"F: {round(row['fat'],1)}g | "
                f"C: {round(row['carbs'],1)}g"
            )

        with col2:
            if st.button("Delete", key=f"delete_{i}"):
                st.session_state.daily_log.pop(i)
                st.rerun()

    df = pd.DataFrame(st.session_state.daily_log)
    totals = df[["calories", "protein", "fat", "carbs"]].sum()

    st.divider()
    st.header("Daily Dashboard")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Calories", round(totals["calories"], 1))
    col2.metric("Protein (g)", round(totals["protein"], 1))
    col3.metric("Fat (g)", round(totals["fat"], 1))
    col4.metric("Carbs (g)", round(totals["carbs"], 1))

    st.divider()
    st.subheader("Progress Toward Goals")

    for macro in DAILY_GOALS:
        percent = totals[macro] / DAILY_GOALS[macro]
        st.write(f"{macro.capitalize()} ({round(totals[macro],1)} / {DAILY_GOALS[macro]})")
        st.progress(min(percent, 1.0))

else:
    st.info("No food logged yet today.")

# =============================
# END DAY
# =============================

st.header("End Day")

if st.button("End Day and Save"):

    if not df.empty:
        append_to_sheet(df)
        st.session_state.daily_log = []
        st.success("Day saved to Google Sheets.")
    else:
        st.warning("No entries to save.")


