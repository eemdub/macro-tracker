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

# Google Sheets authentication
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

gc = gspread.authorize(creds)
sheet = gc.open_by_key(st.secrets["gcp_service_account"]["sheet_id"])
worksheet = sheet.sheet1

if "daily_log" not in st.session_state:
    st.session_state.daily_log = []

if "current_food" not in st.session_state:
    st.session_state.current_food = None

# =============================
# USDA SEARCH
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

def extract_serving_and_macros(food):
    serving_size = food.get("servingSize")
    serving_unit = food.get("servingSizeUnit")
    household = food.get("householdServingFullText")

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

    return serving_size, serving_unit, household, macros

# =============================
# GOOGLE SHEETS SAVE
# =============================

def append_to_sheet(df):
    rows = df.values.tolist()
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")

# =============================
# UI
# =============================

st.title("Daily Macro Tracker")

st.header("Search Food")

food_query = st.text_input("Enter food name")

if st.button("Search"):
    results = search_food(food_query)

    if results:
        st.session_state.search_results = results
    else:
        st.error("No foods found.")

# =============================
# FOOD SELECTION
# =============================

if "search_results" in st.session_state:

    options = {
        f"{food['description']} ({food.get('brandOwner','USDA')})": food
        for food in st.session_state.search_results
    }

    selected_label = st.selectbox("Select correct food:", list(options.keys()))
    selected_food = options[selected_label]

    st.session_state.current_food = selected_food

# =============================
# SERVING DISPLAY + ADD FOOD
# =============================

if st.session_state.current_food:

    food = st.session_state.current_food

    serving_size, serving_unit, household, macros = extract_serving_and_macros(food)

    st.subheader("USDA Serving Information")

    if household and serving_size:
        st.write(f"1 USDA serving = {household} ({serving_size} {serving_unit})")
    elif serving_size:
        st.write(f"1 USDA serving = {serving_size} {serving_unit}")
    else:
        st.write("Serving size not available.")

    servings_eaten = st.number_input(
        "How many servings did you eat?",
        min_value=0.0,
        step=0.5
    )

    if st.button("Add to Daily Log"):

        entry = {
            "date": str(date.today()),
            "food": food["description"],
            "servings": servings_eaten,
            "calories": macros["calories"] * servings_eaten,
            "protein": macros["protein"] * servings_eaten,
            "fat": macros["fat"] * servings_eaten,
            "carbs": macros["carbs"] * servings_eaten
        }

        st.session_state.daily_log.append(entry)
        st.success("Food added.")

        st.session_state.current_food = None

# =============================
# DAILY TOTALS
# =============================

st.header("Today's Log")

df = pd.DataFrame(st.session_state.daily_log)

if not df.empty:

    st.dataframe(df)

    totals = df[["calories", "protein", "fat", "carbs"]].sum()

    st.subheader("Daily Totals")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Calories", round(totals["calories"], 1))
    col2.metric("Protein (g)", round(totals["protein"], 1))
    col3.metric("Fat (g)", round(totals["fat"], 1))
    col4.metric("Carbs (g)", round(totals["carbs"], 1))

# =============================
# END DAY
# =============================

st.header("End Day")

if st.button("End Day and Save"):

    if not df.empty:

        append_to_sheet(df)

        st.session_state.daily_log = []
        st.success("Day saved to Google Sheets and reset.")

    else:
        st.warning("No entries to save.")
