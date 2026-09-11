"""Streamlit observability dashboard — inspects Decision Records and KPI
trajectories across cycles.

Run with: streamlit run observability/dashboard/app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from observability.decision_record import get_records

st.set_page_config(page_title="Flywheel Dashboard", layout="wide")
st.title("Flywheel — Decision Record Dashboard")

records = get_records()
if not records:
    st.info("No decision records yet. Run `python orchestration/cycle.py --cycles N` first.")
else:
    agents = sorted({r["agent"] for r in records})
    selected_agent = st.selectbox("Filter by agent", ["all"] + agents)
    filtered = records if selected_agent == "all" else [r for r in records if r["agent"] == selected_agent]
    st.dataframe(filtered, use_container_width=True)
