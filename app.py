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
daily_ws = sheet.sheet1

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
    return response.json().get("foods")

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

def append_meal(rows):
    daily_ws.append_rows(rows, value_input_option="USER_ENTERED")

# -----------------------------
# SAVED FOODS
# -----------------------------

def load_saved_foods():
    try:
        ws = sheet.worksheet("SavedFoods")
        return pd.DataFrame(ws.get_all_records())
    except:
        return pd.DataFrame(columns=[
            "food","servings","calories","protein","fat","sat_fat","carbs"
        ])

def save_food_to_library(entry):
    ws = sheet.worksheet("SavedFoods")
    ws.append_row([
        entry["food"],
        1,
        entry["calories"],
        entry["protein"],
        entry["fat"],
        entry["sat_fat"],
        entry["carbs"]
    ])

# -----------------------------
# WEIGHT TRACKING
# -----------------------------

def load_weights():
    try:
        ws = sheet.worksheet("Weights")
        return pd.DataFrame(ws.get_all_records())
    except:
        return pd.DataFrame(columns=["date","weight"])

def save_weight(weight):
    ws = sheet.worksheet("Weights")
    ws.append_row([str(date.today()), weight])

# =============================
# UI
# =============================

st.title("Daily Macro Tracker")


# =============================
# LAYOUT
# =============================

left_col, right_col = st.columns([1,1])

# =============================
# LEFT — INPUT
# =============================

with left_col:

    st.header("Add Food")

    entry_mode = st.radio(
        "Entry Method",
        ["Search USDA","Enter Macros Manually"],
        horizontal=True
    )

    # USDA MODE
    if entry_mode == "Search USDA":

        food_query = st.text_input("Search food")
        if st.button("Search"):
            results = search_food(food_query)
            if results:
                st.session_state.search_results = results

        if "search_results" in st.session_state:

            options = {
                f"{f['description']} ({f.get('brandOwner','USDA')})": f
                for f in st.session_state.search_results
            }

            selected = st.selectbox("Select food", list(options.keys()))
            food = options[selected]
            macros = extract_macros(food)

            serving_size = food.get("servingSize")
            serving_unit = food.get("servingSizeUnit")

            servings = st.number_input("Servings eaten", min_value=0.0, step=0.5)

            if serving_size and serving_unit and serving_unit.lower()=="g":
                multiplier = (serving_size/100)*servings
            else:
                multiplier = servings

            if st.button("Add to Current Meal"):
                entry = {
                    "date": today_str,
                    "food": food["description"],
                    "calories": macros["calories"]*multiplier,
                    "protein": macros["protein"]*multiplier,
                    "fat": macros["fat"]*multiplier,
                    "carbs": macros["carbs"]*multiplier,
                    "sat_fat": macros["sat_fat"]*multiplier
                }
                st.session_state.current_meal.append(entry)
                st.success("Added.")

    # MANUAL MODE
    if entry_mode == "Enter Macros Manually":

        saved_df = load_saved_foods()

        if not saved_df.empty:
            options = ["Enter New Food"] + list(saved_df["food"])
            selected = st.selectbox("Saved or New", options)
        else:
            selected = "Enter New Food"

        if selected != "Enter New Food":
            row = saved_df[saved_df["food"]==selected].iloc[0]
            multiplier = st.number_input("Servings", min_value=0.0, step=0.5)

            manual_name = selected
            manual_calories = row["calories"]*multiplier
            manual_protein = row["protein"]*multiplier
            manual_fat = row["fat"]*multiplier
            manual_carbs = row["carbs"]*multiplier
            manual_sat = row["sat_fat"]*multiplier

            st.write(f"Calories: {round(manual_calories,1)}")

        else:
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

            manual_calories = manual_protein*4 + manual_carbs*4 + manual_fat*9
            st.write(f"Calories: {round(manual_calories,1)}")

        if st.button("Add to Current Meal"):
            entry = {
                "date": today_str,
                "food": manual_name,
                "calories": manual_calories,
                "protein": manual_protein,
                "fat": manual_fat,
                "carbs": manual_carbs,
                "sat_fat": manual_sat
            }

            st.session_state.current_meal.append(entry)

            if selected == "Enter New Food":
                save_food_to_library(entry)

            st.success("Added.")

    # SAVE MEAL
    if st.session_state.current_meal:
        st.subheader("Current Meal")
        st.dataframe(pd.DataFrame(st.session_state.current_meal))

        if st.button("Save Meal"):
            rows = [list(item.values()) for item in st.session_state.current_meal]
            append_meal(rows)
            st.session_state.daily_log.extend(st.session_state.current_meal)
            st.session_state.current_meal = []
            st.success("Meal saved.")

# =============================
# RIGHT — DASHBOARD
# =============================

with right_col:

    st.header("Daily Totals")

    df = pd.DataFrame(st.session_state.daily_log)

    if not df.empty:
        totals = df.sum(numeric_only=True)

        def block(label,value,goal):
            over=value>goal
            percent=value/goal

            if over:
                st.markdown(f"<span style='color:red;font-weight:bold'>{label}</span>",unsafe_allow_html=True)
                st.markdown(f"<span style='color:red;font-size:28px;font-weight:bold'>{round(value,1)}</span>",unsafe_allow_html=True)
            else:
                st.markdown(f"**{label}**")
                st.markdown(f"<span style='font-size:28px;font-weight:bold'>{round(value,1)}</span>",unsafe_allow_html=True)

            st.progress(min(percent,1.0))
            st.markdown("<br>",unsafe_allow_html=True)

        block("Calories",totals["calories"],DAILY_GOALS["calories"])
        block("Protein",totals["protein"],DAILY_GOALS["protein"])
        block("Fat",totals["fat"],DAILY_GOALS["fat"])
        block("Carbs",totals["carbs"],DAILY_GOALS["carbs"])
        block("Sat Fat",totals["sat_fat"],DAILY_GOALS["sat_fat"])

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
                f"Sat: {round(row['sat_fat'],1)}g | "
                f"C: {round(row['carbs'],1)}g"
            )

            if high_carb:
                st.markdown(
                    f"<div style='background-color:#ffe6e6;padding:8px;border-radius:6px'>"
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

if st.button("End Day"):
    st.session_state.daily_log=[]
    st.session_state.current_meal=[]
    st.success("Day cleared.")

# =============================
# DAILY WEIGHT
# =============================

st.header("Daily Weight")

weights_df = load_weights()
today_str = str(date.today())

if not weights_df.empty and today_str in weights_df["date"].astype(str).values:
    today_weight = weights_df[weights_df["date"]==today_str]["weight"].iloc[0]
    st.success(f"Today's weight logged: {today_weight}")
else:
    weight_input = st.number_input("Enter today's weight", min_value=0.0, step=0.1)
    if st.button("Save Weight"):
        save_weight(weight_input)
        st.success("Weight saved.")
        st.rerun()

if not weights_df.empty:
    weights_df["date"] = pd.to_datetime(weights_df["date"])
    weights_df = weights_df.sort_values("date")
    st.line_chart(weights_df.set_index("date")["weight"])

st.divider()



