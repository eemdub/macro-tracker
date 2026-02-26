import streamlit as st
import requests
import pandas as pd
from datetime import date

API_KEY = "kdqLV5XDvN6Z3nEYLKlJXHdskFj7GP2aFY7WlgVk"

if "daily_log" not in st.session_state:
    st.session_state.daily_log = []

def search_food(food_name):
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "query": food_name,
        "api_key": API_KEY,
        "pageSize": 1
    }
    response = requests.get(url, params=params)
    data = response.json()
    if not data["foods"]:
        return None
    return data["foods"][0]

def extract_macros(food_data, grams):
    nutrients = food_data["foodNutrients"]
    macros = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}

    for n in nutrients:
        if n["nutrientId"] == 1008:
            macros["calories"] = n["value"]
        elif n["nutrientId"] == 1005:
            macros["carbs"] = n["value"]
        elif n["nutrientId"] == 1003:
            macros["protein"] = n["value"]
        elif n["nutrientId"] == 1004:
            macros["fat"] = n["value"]


    for key in macros:
        macros[key] = macros[key] * grams / 100

    return macros

st.title("Daily Nutrition Tracker")

food_name = st.text_input("Food name")
grams = st.number_input("Amount (grams)", min_value=0.0)

if st.button("Add Food"):
    food = search_food(food_name)
    if food:
        macros = extract_macros(food, grams)
        entry = {
            "date": str(date.today()),
            "food": food_name,
            "grams": grams,
            **macros
        }
        st.session_state.daily_log.append(entry)
        st.success("Food added.")
    else:
        st.error("Food not found.")

df = pd.DataFrame(st.session_state.daily_log)

if not df.empty:
    st.subheader("Today's Entries")
    st.dataframe(df)

    totals = df[["calories", "carbs", "protein", "fat"]].sum()
    st.subheader("Daily Totals")
    st.write(totals)

if st.button("End Day"):
    if not df.empty:
        df.to_csv("macro_history.csv", mode="a", index=False, header=not pd.io.common.file_exists("macro_history.csv"))
        st.session_state.daily_log = []
        st.success("Day saved and reset.")