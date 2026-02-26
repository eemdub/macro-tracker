# ==========================================================
# WATER + WEIGHT ROW
# ==========================================================

row_left, row_right = st.columns([1,2])

# -------- LEFT SIDE --------
with row_left:
    st.header("Water & Weight")

    water_amount = st.number_input("Add water (oz)", 0.0, step=4.0)
    if st.button("Add Water"):
        water_ws.append_row([str(selected_date), water_amount])
        st.cache_data.clear()
        st.rerun()

    st.divider()

    weight_input = st.number_input("Enter weight", 0.0, step=0.1)
    if st.button("Save Weight"):
        weight_ws.append_row([str(selected_date), weight_input])
        st.cache_data.clear()
        st.rerun()

# -------- RIGHT SIDE --------
with row_right:
    st.header("Chart Goes Here")
    st.write("Chart section will render here.")
