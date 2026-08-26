"""24/7 scheduler daemon for incremental data collection."""
import time
import signal
import sys
from typing import Dict, Callable


class LiveScheduler:
    """Runs collectors on scheduled intervals, forever."""

    def __init__(self):
        self.jobs = []
        self.running = False
        self._setup_signals()

    def _setup_signals(self):
        """Handle graceful shutdown."""
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        print("\n[Scheduler] Shutdown signal received. Stopping gracefully...")
        self.running = False
        sys.exit(0)

    def add_job(self, func: Callable, interval_minutes: int, name: str):
        """Add a recurring job."""
        import schedule
        schedule.every(interval_minutes).minutes.do(self._wrap_job, func, name)
        print(f"[Scheduler] Registered '{name}' every {interval_minutes} minutes")

    def add_hourly_job(self, func: Callable, interval_hours: int, name: str):
        """Add a recurring hourly job."""
        import schedule
        schedule.every(interval_hours).hours.do(self._wrap_job, func, name)
        print(f"[Scheduler] Registered '{name}' every {interval_hours} hours")

    def _wrap_job(self, func, name):
        """Wrap job with error handling."""
        print(f"\n[Scheduler] >>> Running '{name}' at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            func()
            print(f"[Scheduler] <<< '{name}' completed")
        except Exception as e:
            print(f"[Scheduler] !!! '{name}' failed: {e}")
        return True  # schedule expects return value

    def run(self):
        """Start the infinite loop."""
        import schedule
        print("[Scheduler] Starting 24/7 live collection...")
        print("[Scheduler] Press Ctrl+C to stop\n")
        self.running = True

        # Run all jobs immediately on startup
        for job in schedule.jobs:
            job.run()

        while self.running:
            schedule.run_pending()
            time.sleep(60)
