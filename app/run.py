# app/run.py

from orchestrator import run_pipeline
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.simplefilter(action='ignore', category=FutureWarning)


if __name__ == "__main__":
    run_pipeline("YYYY-MM-DD")  # replace with actual date(format: YYYY-MM-DD , example: 2025-07-09) or leave as is for today 