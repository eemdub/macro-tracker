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
    "calories": 2000,
    "protein": 130,
    "fat": 70,
    "carbs": 130,
    "sat_fat": 15
}

# =============================
# SESSION STATE
# =============================

if "daily_log" not in st.session_state:
    st.session_state.daily_log = []

if "current_meal" not in st.session_state:
    st.session_state.current_meal = []

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
    return data.get("foods")

def extract_macros(food):
    nutrients = food.get("foodNutrients", [])
    macros = {"calories":0,"protein":0,"fat":0,"carbs":0,"sat_fat":0}

    for n in nutrients:
        if n["nutrientId"] == 1008:
            macros["calories"] = n["value"]
        elif n["nutrientId"] == 1003:
            macros["protein"] = n["value"]
        elif n["nutrientId"] == 1004:
            macros["fat"] = n["value"]
        elif n["nutrientId"] == 1005:
            macros["carbs"] = n["value"]
        elif n["nutrientId"] == 1258:
            macros["sat_fat"] = n["value"]

    return macros

def append_to_sheet(rows):
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")

# =============================
# LAYOUT
# =============================

st.title("Daily Macro Tracker")

left_col, right_col = st.columns([1,1])

# =============================
# LEFT COLUMN — INPUT
# =============================

with left_col:

    st.header("Add Food")

    entry_mode = st.radio(
        "Select Entry Method:",
        ["Search USDA","Enter Macros Manually"],
        horizontal=True
    )

    # -------------------------
    # USDA MODE
    # -------------------------

    if entry_mode == "Search USDA":

        with st.form("search_form"):
            food_query = st.text_input("Enter food name")
            submitted = st.form_submit_button("Search")

        if submitted:
            results = search_food(food_query)
            if results:
                st.session_state.search_results = results
            else:
                st.error("No foods found.")

        if "search_results" in st.session_state:

            options = {
                f"{food['description']} ({food.get('brandOwner','USDA')})": food
                for food in st.session_state.search_results
            }

            selected_label = st.selectbox("Select correct food:", list(options.keys()))
            selected_food = options[selected_label]

            macros = extract_macros(selected_food)

            serving_size = selected_food.get("servingSize")
            serving_unit = selected_food.get("servingSizeUnit")

            if serving_size:
                servings = st.number_input("Servings eaten", min_value=0.0, step=0.5)

                if serving_unit and serving_unit.lower()=="g":
                    multiplier = (serving_size/100)*servings
                else:
                    multiplier = servings
            else:
                servings = st.number_input("Estimated 100g servings", min_value=0.0, step=0.5)
                multiplier = servings

            if st.button("Add to Current Meal"):

                entry = {
                    "date": str(date.today()),
                    "food": selected_food["description"],
                    "calories": macros["calories"]*multiplier,
                    "protein": macros["protein"]*multiplier,
                    "fat": macros["fat"]*multiplier,
                    "carbs": macros["carbs"]*multiplier,
                    "sat_fat": macros.get("sat_fat",0)*multiplier
                }

                st.session_state.current_meal.append(entry)
                st.success("Added to meal.")

    # -------------------------
    # MANUAL MODE
    # -------------------------

    if entry_mode == "Enter Macros Manually":

        manual_name = st.text_input("Food name")

        r1c1,r1c2 = st.columns(2)
        with r1c1:
            manual_protein = st.number_input("Protein (g)", min_value=0.0)
        with r1c2:
            manual_carbs = st.number_input("Carbs (g)", min_value=0.0)

        r2c1,r2c2 = st.columns(2)
        with r2c1:
            manual_fat = st.number_input("Fat (g)", min_value=0.0)
        with r2c2:
            manual_sat = st.number_input("Sat Fat (g)", min_value=0.0)

        calories = manual_protein*4 + manual_carbs*4 + manual_fat*9
        st.write(f"Calories: {round(calories,1)}")

        if st.button("Add to Current Meal"):

            entry = {
                "date": str(date.today()),
                "food": manual_name,
                "calories": calories,
                "protein": manual_protein,
                "fat": manual_fat,
                "carbs": manual_carbs,
                "sat_fat": manual_sat
            }

            st.session_state.current_meal.append(entry)
            st.success("Added to meal.")

    # -------------------------
    # SAVE MEAL
    # -------------------------

    if st.session_state.current_meal:

        st.subheader("Current Meal")

        meal_df = pd.DataFrame(st.session_state.current_meal)
        st.dataframe(meal_df)

        if st.button("Save Meal to Sheet"):

            rows = [list(item.values()) for item in st.session_state.current_meal]
            append_to_sheet(rows)

            st.session_state.daily_log.extend(st.session_state.current_meal)
            st.session_state.current_meal = []

            st.success("Meal saved.")

# =============================
# RIGHT COLUMN — DASHBOARD
# =============================

with right_col:

    st.header("Daily Totals")

    df = pd.DataFrame(st.session_state.daily_log)

    if not df.empty:

        totals = df.sum(numeric_only=True)

        def macro_block(label,value,goal):
            percent=value/goal
            over=value>goal

            if over:
                st.markdown(f"<span style='color:red;font-weight:bold'>{label}</span>",unsafe_allow_html=True)
                st.markdown(f"<span style='color:red;font-size:28px;font-weight:bold'>{round(value,1)}</span>",unsafe_allow_html=True)
            else:
                st.markdown(f"**{label}**")
                st.markdown(f"<span style='font-size:28px;font-weight:bold'>{round(value,1)}</span>",unsafe_allow_html=True)

            st.progress(min(percent,1.0))
            st.markdown("<br>",unsafe_allow_html=True)

        macro_block("Calories",totals["calories"],DAILY_GOALS["calories"])
        macro_block("Protein",totals["protein"],DAILY_GOALS["protein"])
        macro_block("Fat",totals["fat"],DAILY_GOALS["fat"])
        macro_block("Carbs",totals["carbs"],DAILY_GOALS["carbs"])
        macro_block("Sat Fat",totals["sat_fat"],DAILY_GOALS["sat_fat"])

# =============================
# FOOD LOG
# =============================

st.divider()
st.header("Today's Log")

if not df.empty:
    st.dataframe(df)

# =============================
# END DAY
# =============================

if st.button("End Day"):
    st.session_state.daily_log=[]
    st.session_state.current_meal=[]
    st.success("Day cleared.")
