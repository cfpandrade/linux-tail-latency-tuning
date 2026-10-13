"""Smoke test: checks the project layout and the analysis environment."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REQUIRED = ["numpy", "scipy", "pandas", "matplotlib", "sklearn", "skopt", "shap"]


def test_layout():
    from scripts.common import DATA_DIR, FIGURES_DIR
    assert DATA_DIR.is_dir()
    assert FIGURES_DIR.is_dir()


def test_imports():
    missing = []
    for name in REQUIRED:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    assert not missing, f"missing packages: {missing}"


if __name__ == "__main__":
    failures = 0
    for fn in (test_layout, test_imports):
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {fn.__name__}: {e}")
    sys.exit(1 if failures else 0)
