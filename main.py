import streamlit as st

# ── Single entry point: Race Lab is the whole app ──
race_lab = st.Page("pages_vibe/01_Race_Lab.py", title="Race Lab", icon="⚡", default=True)

pg = st.navigation([race_lab])
st.set_page_config(page_title="Pace Yourself", page_icon="🏁", layout="wide")
pg.run()
