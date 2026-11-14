"""Streamlit entry point. Run from the project root with the local virtual environment."""

from src.studio.runtime import ensure_generation_compatibility

ensure_generation_compatibility()

from src.studio.views import main

main()
