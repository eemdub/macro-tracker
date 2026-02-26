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
