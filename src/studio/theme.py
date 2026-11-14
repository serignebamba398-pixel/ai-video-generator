"""Visual styling only; workflow and persistence belong to other modules."""

from pathlib import Path

import streamlit as st


def apply_theme():
    stylesheet = Path(__file__).with_name("studio.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{stylesheet}</style>", unsafe_allow_html=True)
