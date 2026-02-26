import streamlit as st
import pandas as pd
import requests
import uuid
import altair as alt
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
saved_ws = sheet.worksheet("Saved Foods")
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
def load_saved_foods():
    df = pd.DataFrame(saved_ws.get_all_records())
    if df.empty:
        return df
    numeric_cols = ["calories","protein","fat","sat_fat","carbs","fiber"]
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
# TOP ROW
# ==========================================================

col1, col2, col3 = st.columns([1,1,1])

with col1:
    selected_date = st.date_input("Select Date", date.today())
    selected_date_str = str(selected_date)

with col2:
    st.button("Weekly Review")

with col3:
    st.markdown("### 🔥 Streaks")

foods_df = load_foods()
water_df = load_water()
weights_df = load_weights()

# ==========================================================
# FOOD + MACRO ROW
# ==========================================================

left, right = st.columns([1,1])
day_df = foods_df[foods_df["date"] == selected_date_str] if not foods_df.empty else pd.DataFrame()

with left:
    st.header("Add Food")

    mode = st.radio("Entry Method", ["Search USDA","Manual / Saved"], horizontal=True)

    # USDA
    if mode == "Search USDA":
        query = st.text_input("Search food")

        if st.button("Search"):
            results = requests.get(
                "https://api.nal.usda.gov/fdc/v1/foods/search",
                params={"query": query, "api_key": USDA_API_KEY, "pageSize":5}
            ).json().get("foods", [])

            st.session_state.search_results = results

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

    # MANUAL / SAVED
    else:
        saved_df = load_saved_foods()
        search = st.text_input("Search Saved Foods")

        if not saved_df.empty:
            filtered = saved_df[
                saved_df["food"].str.contains(search, case=False, na=False)
            ] if search else saved_df

            options = ["New Food"] + filtered["food"].tolist()
        else:
            options = ["New Food"]

        selection = st.selectbox("Select", options)

        if selection != "New Food":
            row = saved_df[saved_df["food"]==selection].iloc[0]
            servings = st.number_input("Servings", 1.0)

            if st.button("Add Saved"):
                daily_ws.append_row([
                    str(uuid.uuid4()),
                    selected_date_str,
                    selection,
                    servings,
                    row["calories"]*servings,
                    row["protein"]*servings,
                    row["fat"]*servings,
                    row["sat_fat"]*servings,
                    row["carbs"]*servings,
                    row["fiber"]*servings
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

            calories = protein*4 + carbs*4 + fat*9

            if st.button("Add Manual"):
                daily_ws.append_row([
                    str(uuid.uuid4()),
                    selected_date_str,
                    name,
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

with right:
    st.header("Daily Totals")
    if not day_df.empty:
        totals = day_df.sum(numeric_only=True)
        labels = []
        values = []
        for k in DAILY_GOALS:
            remaining = DAILY_GOALS[k] - totals.get(k,0)
            labels.append(f"{k}\n{round(remaining,1)} left")
            values.append(min(totals.get(k,0)/DAILY_GOALS[k],1.5))
        st.bar_chart(pd.DataFrame({"%":values}, index=labels))

# ==========================================================
# 7 DAY WATER & WEIGHT CHART (CORRECT DUAL AXIS VERSION)
# ==========================================================

with row_right:
    st.header("7 Day Water & Weight")

    start_date = pd.to_datetime(selected_date) - timedelta(days=6)

    water_last7 = water_df[water_df["date"] >= start_date].copy() if not water_df.empty else pd.DataFrame()
    weight_last7 = weights_df[weights_df["date"] >= start_date].copy() if not weights_df.empty else pd.DataFrame()

    # Prepare clean combined dataframe
    combined = pd.DataFrame()

    if not water_last7.empty:
        water_last7["date"] = water_last7["date"].dt.date
        combined = water_last7[["date", "water"]].copy()

    if not weight_last7.empty:
        weight_last7["date"] = weight_last7["date"].dt.date
        if combined.empty:
            combined = weight_last7[["date", "weight"]].copy()
        else:
            combined = pd.merge(combined, weight_last7[["date","weight"]], on="date", how="outer")

    if not combined.empty:

        base = alt.Chart(combined).encode(
            x=alt.X("date:T", axis=alt.Axis(format="%b %d"))
        )

        # WATER LAYER
        water_line = base.mark_line(
            strokeWidth=4,
            color="blue"
        ).encode(
            y=alt.Y(
                "water:Q",
                scale=alt.Scale(domain=[0,80]),
                axis=alt.Axis(title="Water (oz)", orient="left")
            )
        )

        water_points = base.mark_point(
            size=200,
            color="blue"
        ).encode(
            y="water:Q"
        )

        # WEIGHT LAYER
        weight_line = base.mark_line(
            strokeWidth=4,
            color="green"
        ).encode(
            y=alt.Y(
                "weight:Q",
                scale=alt.Scale(domain=[300,400]),
                axis=alt.Axis(title="Weight (lbs)", orient="right")
            )
        )

        weight_points = base.mark_point(
            size=200,
            color="green"
        ).encode(
            y="weight:Q"
        )

        chart = alt.layer(
            water_line,
            water_points,
            weight_line,
            weight_points
        ).resolve_scale(
            y="independent"
        )

        st.altair_chart(chart, use_container_width=True)

    else:
        st.info("No data available for last 7 days.")

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

colA, colB = st.columns([1,1])

with colA:
    if st.button("Save Note"):
        notes_ws.append_row([selected_date_str, note_text])
        load_notes.clear()
        st.success("Saved")

with colB:
    if st.button("End Day"):
        st.success("Day Complete")

