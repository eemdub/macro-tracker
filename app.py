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
        "carbs": 0,
        "sat_fat": 0
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
        elif n["nutrientId"] == 1258:
            macros["sat_fat"] = n["value"]

    return macros

def append_to_sheet(df):
    rows = df.values.tolist()
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")

# =============================
# LAYOUT
# =============================

st.title("Daily Macro Tracker")

left_col, right_col = st.columns([1, 1])

# =============================
# LEFT COLUMN (INPUT)
# =============================

with left_col:

    st.header("Add Food")

    entry_mode = st.radio(
        "Select Entry Method:",
        ["Search USDA", "Enter Macros Manually"],
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
            st.session_state.current_food = selected_food

        if st.session_state.current_food:

            food = st.session_state.current_food
            macros = extract_macros(food)

            serving_size = food.get("servingSize")
            serving_unit = food.get("servingSizeUnit")
            household = food.get("householdServingFullText")

            st.subheader("Serving Information")

            if serving_size:

                if household:
                    st.write(f"1 USDA serving = {household} ({serving_size} {serving_unit})")
                else:
                    st.write(f"1 USDA serving = {serving_size} {serving_unit}")

                servings = st.number_input(
                    "How many servings did you eat?",
                    min_value=0.0,
                    step=0.5
                )

                multiplier = servings

    # 🔥 FIX: USDA nutrients are often per 100g
    if serving_unit and serving_unit.lower() == "g":
        multiplier = (serving_size / 100) * servings
    else:
        multiplier = servings

            else:
                st.warning("No USDA serving size available.")
                st.write("Nutrition values are based on 100g.")
                servings = st.number_input(
                    "Estimated number of 100g servings:",
                    min_value=0.0,
                    step=0.5
                )
                multiplier = servings

            if st.button("Add to Daily Log"):

                entry = {
                    "date": str(date.today()),
                    "food": food["description"],
                    "calories": macros["calories"] * multiplier,
                    "protein": macros["protein"] * multiplier,
                    "fat": macros["fat"] * multiplier,
                    "carbs": macros["carbs"] * multiplier,
                    "sat_fat": macros.get("sat_fat", 0) * multiplier
                }

                st.session_state.daily_log.append(entry)
                st.success("Food added.")
                st.session_state.current_food = None

    # -------------------------
    # MANUAL MODE
    # -------------------------

    if entry_mode == "Enter Macros Manually":

        st.subheader("Manual Macro Entry")

        manual_name = st.text_input("Food name")

        # Row 1
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            manual_protein = st.number_input("Protein (g)", min_value=0.0)
        with r1c2:
            manual_carbs = st.number_input("Carbs (g)", min_value=0.0)

        # Row 2
        r2c1, r2c2 = st.columns(2)
        with r2c1:
            manual_fat = st.number_input("Fat (g)", min_value=0.0)
        with r2c2:
            manual_sat_fat = st.number_input("Saturated Fat (g)", min_value=0.0)

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
                "carbs": manual_carbs,
                "sat_fat": manual_sat_fat
            }

            st.session_state.daily_log.append(entry)
            st.success("Manual entry added.")

# =============================
# RIGHT COLUMN (DASHBOARD)
# =============================

with right_col:

    st.header("Daily Dashboard")

    df = pd.DataFrame(st.session_state.daily_log)

    if not df.empty:

        if "sat_fat" not in df.columns:
            df["sat_fat"] = 0

        totals = df[["calories","protein","fat","carbs","sat_fat"]].sum()

        def macro_block(label, value, goal):
            percent = value / goal
            over_goal = value > goal

            if over_goal:
                st.markdown(
                    f"<div style='color:red;font-weight:bold'>{label}</div>",
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"<div style='color:red;font-size:28px;font-weight:bold'>{round(value,1)}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(f"**{label}**")
                st.markdown(
                    f"<div style='font-size:28px;font-weight:bold'>{round(value,1)}</div>",
                    unsafe_allow_html=True
                )

            st.progress(min(percent, 1.0))
            st.markdown("<br>", unsafe_allow_html=True)

        macro_block("Calories", totals["calories"], DAILY_GOALS["calories"])
        macro_block("Protein (g)", totals["protein"], DAILY_GOALS["protein"])
        macro_block("Fat (g)", totals["fat"], DAILY_GOALS["fat"])
        macro_block("Carbs (g)", totals["carbs"], DAILY_GOALS["carbs"])
        macro_block("Sat Fat (g)", totals["sat_fat"], DAILY_GOALS["sat_fat"])

    else:
        st.info("No food logged yet today.")

# =============================
# FOOD LOG
# =============================

st.divider()
st.header("Today's Log")

df = pd.DataFrame(st.session_state.daily_log)

if not df.empty:

    for i, row in df.iterrows():

        col1, col2 = st.columns([6, 1])
        high_carb = row["carbs"] > 30

        with col1:
            food_display = f"**{row['food']}**"

            macro_text = (
                f"{round(row['calories'],1)} cal | "
                f"P: {round(row['protein'],1)}g | "
                f"F: {round(row['fat'],1)}g | "
                f"Sat: {round(row.get('sat_fat',0),1)}g | "
                f"C: {round(row['carbs'],1)}g"
            )

            if high_carb:
                st.markdown(
                    f"<div style='background-color:#ffe6e6;padding:8px;border-radius:5px'>"
                    f"{food_display} | {macro_text}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(f"{food_display} | {macro_text}")

        with col2:
            if st.button("Delete", key=f"delete_{i}"):
                st.session_state.daily_log.pop(i)
                st.rerun()

else:
    st.info("No entries yet.")

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

