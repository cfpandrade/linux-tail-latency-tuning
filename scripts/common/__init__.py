"""Shared helpers for analysis scripts (paths, loading, plotting)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
FIGURES_DIR = ROOT / "figures"
