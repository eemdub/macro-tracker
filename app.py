import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta
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

DAILY_GOALS = {
    "calories": 2000,
    "protein": 130,
    "fat": 70,
    "carbs": 130,
    "sat_fat": 15
}

WATER_GOAL = 75

today_str = str(date.today())

# =============================
# HELPERS
# =============================

@st.cache_data(ttl=60)
def load_today_meals():
    try:
        df = pd.DataFrame(daily_ws.get_all_records())
        if df.empty:
            return []
        df["date"] = df["date"].astype(str)
        return df[df["date"] == today_str].to_dict("records")
    except:
        return []

def rewrite_daily_sheet(data):
    daily_ws.clear()
    daily_ws.append_row(
        ["date","food","servings","calories","protein","fat","sat_fat","carbs"]
    )
    if data:
        rows = []
        for item in data:
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
        daily_ws.append_rows(rows, value_input_option="USER_ENTERED")

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

# =============================
# WATER
# =============================

@st.cache_data(ttl=60)
def load_water_df():
    try:
        df = pd.DataFrame(water_ws.get_all_records())
        if df.empty:
            return pd.DataFrame(columns=["date","water"])
        df["date"] = pd.to_datetime(df["date"])
        df["water"] = df["water"].astype(float)
        return df.sort_values("date")
    except:
        return pd.DataFrame(columns=["date","water"])

def get_today_water(df):
    today = df[df["date"] == pd.to_datetime(today_str)]
    if today.empty:
        return 0
    return float(today["water"].iloc[0])

def update_water(amount):
    df = load_water_df()

    if pd.to_datetime(today_str) not in df["date"].values:
        water_ws.append_row([today_str, amount])
    else:
        row_index = df.index[df["date"]==pd.to_datetime(today_str)][0] + 2
        current = df.loc[df["date"]==pd.to_datetime(today_str),"water"].iloc[0]
        water_ws.update_cell(row_index,2,float(current)+amount)

    load_water_df.clear()

# =============================
# SESSION STATE
# =============================

if "daily_log" not in st.session_state:
    st.session_state.daily_log = load_today_meals()

if "current_meal" not in st.session_state:
    st.session_state.current_meal = []

# =============================
# UI
# =============================

st.title("Daily Macro & Water Tracker")

# ==========================================================
# TOP ROW — FOOD + MACROS
# ==========================================================

top_left, top_right = st.columns([1,1])

# ---------- FOOD ENTRY ----------
with top_left:

    st.header("Add Food")

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

        servings = st.number_input("Servings eaten", min_value=0.0, step=0.5)

        if st.button("Add to Current Meal"):
            entry = {
                "date": today_str,
                "food": food["description"],
                "servings": servings,
                "calories": macros["calories"] * servings,
                "protein": macros["protein"] * servings,
                "fat": macros["fat"] * servings,
                "carbs": macros["carbs"] * servings,
                "sat_fat": macros["sat_fat"] * servings
            }
            st.session_state.current_meal.append(entry)
            st.success("Added.")

    if st.session_state.current_meal:
        st.dataframe(pd.DataFrame(st.session_state.current_meal))

        if st.button("Save Meal"):
            st.session_state.daily_log.extend(st.session_state.current_meal)
            rewrite_daily_sheet(st.session_state.daily_log)
            st.session_state.current_meal = []
            st.success("Meal saved.")
            st.rerun()

# ---------- MACRO GRAPH ----------
with top_right:

    st.header("Macro Totals")

    df = pd.DataFrame(st.session_state.daily_log)

    if not df.empty:
        totals = df.sum(numeric_only=True)

        chart_data = pd.DataFrame({
            "Macro":[
                f"Calories\n{round(totals['calories'],1)}",
                f"Protein\n{round(totals['protein'],1)}g",
                f"Fat\n{round(totals['fat'],1)}g",
                f"Carbs\n{round(totals['carbs'],1)}g",
                f"Sat Fat\n{round(totals['sat_fat'],1)}g"
            ],
            "Percent":[
                totals["calories"]/DAILY_GOALS["calories"],
                totals["protein"]/DAILY_GOALS["protein"],
                totals["fat"]/DAILY_GOALS["fat"],
                totals["carbs"]/DAILY_GOALS["carbs"],
                totals["sat_fat"]/DAILY_GOALS["sat_fat"]
            ]
        })

        st.bar_chart(chart_data.set_index("Macro"))

# ==========================================================
# SECOND ROW — WATER + 7 DAY GRAPH
# ==========================================================

water_left, water_right = st.columns([1,1])

water_df = load_water_df()
today_water = get_today_water(water_df)

# ---------- WATER ENTRY ----------
with water_left:

    st.header("Water Intake")

    water_add = st.number_input("Add water (oz)", min_value=0.0, step=4.0)

    if st.button("Add Water"):
        update_water(water_add)
        st.success("Water added.")
        st.rerun()

    st.markdown(f"**{round(today_water,1)} oz / {WATER_GOAL} oz**")
    st.progress(min(today_water/WATER_GOAL,1.0))

# ---------- 7 DAY WATER GRAPH ----------
with water_right:

    st.header("Water Tracker")

    if not water_df.empty:
        last_7 = water_df[water_df["date"] >= pd.to_datetime(today_str) - timedelta(days=6)]
        st.line_chart(last_7.set_index("date")["water"])

# ==========================================================
# TODAY'S LOG
# ==========================================================

st.divider()
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
                rewrite_daily_sheet(st.session_state.daily_log)
                st.rerun()

if st.button("End Day"):
    st.session_state.daily_log = []
    rewrite_daily_sheet([])
    st.success("Day cleared.")
    st.rerun()

