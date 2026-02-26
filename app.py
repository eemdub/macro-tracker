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

today_str = str(date.today())

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
    params = {"query": food_name, "api_key": USDA_API_KEY, "pageSize": 5}
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

# =============================
# SAVED FOODS
# =============================

def load_saved_foods():
    try:
        ws = sheet.worksheet("Saved Foods")
        return pd.DataFrame(ws.get_all_records())
    except:
        return pd.DataFrame(columns=[
            "food","servings","calories","protein","fat","sat_fat","carbs"
        ])

def save_food_to_library(entry):
    ws = sheet.worksheet("Saved Foods")
    ws.append_row([
        entry["food"],
        1,
        entry["calories"] / entry["servings"],
        entry["protein"] / entry["servings"],
        entry["fat"] / entry["servings"],
        entry["sat_fat"] / entry["servings"],
        entry["carbs"] / entry["servings"]
    ])

# =============================
# WEIGHTS
# =============================

def load_weights():
    try:
        ws = sheet.worksheet("Weights")
        return pd.DataFrame(ws.get_all_records())
    except:
        return pd.DataFrame(columns=["date","weight"])

def save_weight(weight):
    ws = sheet.worksheet("Weights")
    ws.append_row([today_str, weight])

# =============================
# UI
# =============================

st.title("Daily Macro Tracker")

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

    # ---------- USDA ----------
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

            selected_label = st.selectbox("Select food", list(options.keys()))
            food = options[selected_label]
            macros = extract_macros(food)

            serving_size = food.get("servingSize")
            serving_unit = food.get("servingSizeUnit")

            servings = st.number_input("Servings eaten", min_value=0.0, step=0.5)

            if serving_size and serving_unit and serving_unit.lower()=="g":
                multiplier = (serving_size/100) * servings
            else:
                multiplier = servings

            if st.button("Add to Current Meal"):
                entry = {
                    "date": today_str,
                    "food": food["description"],
                    "servings": servings,
                    "calories": macros["calories"] * multiplier,
                    "protein": macros["protein"] * multiplier,
                    "fat": macros["fat"] * multiplier,
                    "carbs": macros["carbs"] * multiplier,
                    "sat_fat": macros["sat_fat"] * multiplier
                }
                st.session_state.current_meal.append(entry)
                st.success("Added.")

    # ---------- MANUAL ----------
    if entry_mode == "Enter Macros Manually":

        saved_df = load_saved_foods()

        if not saved_df.empty:
            options = ["Enter New Food"] + list(saved_df["food"])
            selected = st.selectbox("Saved or New", options)
        else:
            selected = "Enter New Food"

        if selected != "Enter New Food":

            row = saved_df[saved_df["food"]==selected].iloc[0]
            servings = st.number_input("Servings eaten", min_value=0.0, step=0.5)

            manual_name = selected
            manual_calories = row["calories"] * servings
            manual_protein = row["protein"] * servings
            manual_fat = row["fat"] * servings
            manual_carbs = row["carbs"] * servings
            manual_sat = row["sat_fat"] * servings

        else:

            manual_name = st.text_input("Food name")

            st.markdown("### Macros Per 1 Serving")

            r1c1, r1c2 = st.columns(2)
            with r1c1:
                per_protein = st.number_input("Protein (g)", min_value=0.0)
            with r1c2:
                per_carbs = st.number_input("Carbs (g)", min_value=0.0)

            r2c1, r2c2 = st.columns(2)
            with r2c1:
                per_fat = st.number_input("Fat (g)", min_value=0.0)
            with r2c2:
                per_sat = st.number_input("Sat Fat (g)", min_value=0.0)

            servings = st.number_input("Servings eaten", min_value=1.0, step=0.5)

            manual_protein = per_protein * servings
            manual_carbs = per_carbs * servings
            manual_fat = per_fat * servings
            manual_sat = per_sat * servings

            manual_calories = (
                per_protein*4 + per_carbs*4 + per_fat*9
            ) * servings

        if st.button("Add to Current Meal"):

            entry = {
                "date": today_str,
                "food": manual_name,
                "servings": servings,
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

    # ---------- SAVE MEAL ----------
    if st.session_state.current_meal:

        st.subheader("Current Meal")
        st.dataframe(pd.DataFrame(st.session_state.current_meal))

        if st.button("Save Meal"):

            rows = []
            for item in st.session_state.current_meal:
                rows.append([
                    item["date"],
                    item["food"],
                    item["servings"],
                    item["calories"],
                    item["protein"],
                    item["fat"],
                    item["sat_fat"],
                    item["carbs"]
                ])

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
            percent = value/goal
            over = value>goal

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

# =============================
# TODAY'S LOG + DELETE
# =============================

st.header("Today's Log")

df = pd.DataFrame(st.session_state.daily_log)

if not df.empty:

    for i, row in df.iterrows():

        col1, col2 = st.columns([6,1])

        with col1:
            st.markdown(
                f"**{row['food']}** | "
                f"{round(row['calories'],1)} cal | "
                f"P:{round(row['protein'],1)}g | "
                f"F:{round(row['fat'],1)}g | "
                f"Sat:{round(row['sat_fat'],1)}g | "
                f"C:{round(row['carbs'],1)}g"
            )

        with col2:
            if st.button("Delete", key=f"del_{i}"):
                st.session_state.daily_log.pop(i)
                st.rerun()

else:
    st.info("No entries yet.")

if st.button("End Day"):
    st.session_state.daily_log=[]
    st.session_state.current_meal=[]
    st.success("Day cleared.")

# =============================
# WEIGHT (BOTTOM)
# =============================

st.divider()
st.header("Daily Weight")

weights_df = load_weights()

if not weights_df.empty and today_str in weights_df["date"].astype(str).values:
    today_weight = weights_df[weights_df["date"]==today_str]["weight"].iloc[0]
    st.success(f"Today's weight: {today_weight}")
else:
    weight_input = st.number_input("Enter today's weight", min_value=0.0, step=0.1)
    if st.button("Save Weight"):
        save_weight(weight_input)
        st.success("Weight saved.")
        st.rerun()

if not weights_df.empty:
    weights_df["date"] = pd.to_datetime(weights_df["date"])
    weights_df = weights_df.sort_values("date")
    st.subheader("Weight Trend")
    st.line_chart(weights_df.set_index("date")["weight"])

