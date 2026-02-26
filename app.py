import streamlit as st
import requests
import pandas as pd
import uuid
from datetime import date, datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

if st.button("RUN ENTRY_ID MIGRATION"):
    import streamlit as st
import uuid
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.title("Backfill entry_id Migration")

# --- AUTH ---
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

gc = gspread.authorize(creds)
sheet = gc.open_by_key(st.secrets["gcp_service_account"]["sheet_id"])
daily_ws = sheet.worksheet("Daily Foods")

if st.button("Run Migration"):

    records = daily_ws.get_all_records()
    df = pd.DataFrame(records)

    if df.empty:
        st.warning("No rows found.")
        st.stop()

    if "entry_id" not in df.columns:
        st.error("Add 'entry_id' column as FIRST column before running.")
        st.stop()

    updates = 0

    for i, row in df.iterrows():
        if not row["entry_id"]:
            new_id = str(uuid.uuid4())
            sheet_row = i + 2  # header row offset
            daily_ws.update_cell(sheet_row, 1, new_id)
            updates += 1

    st.success(f"Backfilled {updates} entry_ids.")

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

# =============================
# DATE SELECTOR (1.B)
# =============================

selected_date = st.date_input("Select Date", date.today())
selected_date_str = str(selected_date)

# =============================
# HELPERS
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
    return df

@st.cache_data(ttl=60)
def load_weights():
    df = pd.DataFrame(weight_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["weight"] = df["weight"].astype(float)
    return df.sort_values("date")

@st.cache_data(ttl=60)
def load_notes():
    df = pd.DataFrame(notes_ws.get_all_records())
    if df.empty:
        return df
    df["date"] = df["date"].astype(str)
    return df

def delete_entry(entry_id):
    df = load_foods()
    row_index = df.index[df["entry_id"] == entry_id][0] + 2
    daily_ws.delete_rows(row_index)
    load_foods.clear()

def add_entry(entry):
    daily_ws.append_row(entry)
    load_foods.clear()

# =============================
# USDA SEARCH (with Fiber)
# =============================

def search_food(food_name):
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {"query": food_name, "api_key": USDA_API_KEY, "pageSize": 5}
    response = requests.get(url, params=params)
    return response.json().get("foods")

def extract_macros(food):
    nutrients = food.get("foodNutrients", [])
    macros = {"calories":0,"protein":0,"fat":0,"carbs":0,"sat_fat":0,"fiber":0}
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
        elif n["nutrientId"] == 1079:
            macros["fiber"] = n["value"]
    return macros

# =============================
# MAIN UI
# =============================

st.title("Advanced Health Tracker")

foods_df = load_foods()
day_df = foods_df[foods_df["date"] == selected_date_str] if not foods_df.empty else pd.DataFrame()

# ==========================================================
# FOOD ENTRY
# ==========================================================

st.header("Add Food")

food_query = st.text_input("Search food")

if st.button("Search"):
    results = search_food(food_query)
    st.session_state.search_results = results

if "search_results" in st.session_state:
    options = {
        f"{f['description']}": f
        for f in st.session_state.search_results
    }

    selected_label = st.selectbox("Select food", list(options.keys()))
    food = options[selected_label]
    macros = extract_macros(food)

    servings = st.number_input("Servings", min_value=0.0, step=0.5)

    if st.button("Add"):
        entry = [
            str(uuid.uuid4()),
            selected_date_str,
            food["description"],
            servings,
            macros["calories"]*servings,
            macros["protein"]*servings,
            macros["fat"]*servings,
            macros["sat_fat"]*servings,
            macros["carbs"]*servings,
            macros["fiber"]*servings
        ]
        add_entry(entry)
        st.rerun()

# ==========================================================
# DAILY TOTALS + REMAINING + PROJECTION
# ==========================================================

if not day_df.empty:

    totals = day_df.sum(numeric_only=True)

    st.subheader("Totals")

    st.write(totals)

    st.subheader("Remaining Today")

    for k in DAILY_GOALS:
        remaining = DAILY_GOALS[k] - totals.get(k,0)
        st.write(f"{k}: {round(remaining,1)}")

    # Projected end
    now = datetime.now()
    hours_passed = now.hour + now.minute/60
    projected = (totals["calories"] / max(hours_passed,1)) * 24
    st.subheader("Projected Day End Calories")
    st.write(round(projected,0))

# ==========================================================
# STREAKS (3.A)
# ==========================================================

water_df = load_water()

if not water_df.empty:
    streak = 0
    for i in range(len(water_df)-1, -1, -1):
        if water_df.iloc[i]["water"] >= WATER_GOAL:
            streak += 1
        else:
            break
    st.write(f"Water streak: {streak} days")

# ==========================================================
# 7-DAY AVERAGES (2.D)
# ==========================================================

weights_df = load_weights()

if not weights_df.empty:
    weights_df["rolling_avg"] = weights_df["weight"].rolling(7).mean()
    st.line_chart(weights_df.set_index("date")[["weight","rolling_avg"]])

# ==========================================================
# NOTES (3.C)
# ==========================================================

notes_df = load_notes()

today_note = ""
if not notes_df.empty:
    row = notes_df[notes_df["date"] == selected_date_str]
    if not row.empty:
        today_note = row["notes"].iloc[0]

new_note = st.text_area("Daily Notes", today_note)

if st.button("Save Note"):
    if notes_df.empty or selected_date_str not in notes_df["date"].values:
        notes_ws.append_row([selected_date_str, new_note])
    else:
        idx = notes_df.index[notes_df["date"]==selected_date_str][0] + 2
        notes_ws.update_cell(idx,2,new_note)
    load_notes.clear()
    st.success("Saved")

# ==========================================================
# WEEKLY REVIEW (3.B)
# ==========================================================

if st.button("Weekly Review"):
    last_7 = foods_df[pd.to_datetime(foods_df["date"]) >= datetime.now()-timedelta(days=7)]
    if not last_7.empty:
        st.write("7-day avg calories:", round(last_7["calories"].mean(),1))
        st.write("7-day avg protein:", round(last_7["protein"].mean(),1))

