"""Scheduler module — APScheduler cron for weekly automated runs."""
import os
import subprocess
import sys
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


def run_pipeline():
    """Execute the full DealRadar pipeline."""
    print(f"[SCHEDULER] Starting scheduled run at {datetime.now(timezone.utc).isoformat()}")
    try:
        result = subprocess.run(
            [sys.executable, "run.py", "--phase=all"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"[SCHEDULER] Pipeline completed successfully")
        else:
            print(f"[SCHEDULER] Pipeline failed with code {result.returncode}")
            print(result.stderr[-500:] if result.stderr else "")
    except Exception as e:
        print(f"[SCHEDULER] Pipeline run error: {e}")


def start_scheduler():
    """Start the APScheduler blocking scheduler (for production)."""
    scheduler = BlockingScheduler()

    # Run every Monday at 7:00am
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(day_of_week="mon", hour=7, minute=0),
        id="dealradar_weekly",
        name="DealRadar Weekly Pipeline",
        replace_existing=True,
    )

    print("[SCHEDULER] Started. Next run: Monday 7:00am")
    print("[SCHEDULER] Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[SCHEDULER] Stopped.")
        scheduler.shutdown()


if __name__ == "__main__":
    # Run directly for testing: python -m src.scheduler
    if len(sys.argv) > 1 and sys.argv[1] == "--run-now":
        run_pipeline()
    else:
        start_scheduler()