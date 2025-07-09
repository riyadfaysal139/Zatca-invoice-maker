# app/run.py

from orchestrator import run_pipeline
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.simplefilter(action='ignore', category=FutureWarning)


if __name__ == "__main__":
    run_pipeline("2025-07-05")  # You can change the date anytime