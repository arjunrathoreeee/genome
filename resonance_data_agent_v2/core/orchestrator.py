"""Orchestrator - coordinates all collectors in init or live mode."""
import time
from core.config import Config
from core.compiler import DataCompiler
from core.supabase_client import SupabaseClient
from core.state_manager import StateManager
from core.scheduler import LiveScheduler
from collectors.reddit_collector import RedditCollector
from collectors.youtube_collector import YouTubeCollector
from collectors.kaggle_collector import KaggleCollector
from collectors.huggingface_collector import HuggingFaceCollector
from collectors.scraper_collector import ScraperCollector


class Orchestrator:
    def __init__(self, config_path="config.yaml"):
        self.config = Config(config_path)
        self.supabase = SupabaseClient(self.config)
        self.state = StateManager(self.supabase)
        self.compiler = None
        self.collectors = {}
        self._init_collectors()

    def _init_collectors(self):
        mapping = {
            "reddit": RedditCollector,
            "youtube": YouTubeCollector,
            "kaggle": KaggleCollector,
            "huggingface": HuggingFaceCollector,
            "scraper": ScraperCollector,
        }
        for name, cls in mapping.items():
            if self.config.is_enabled(name):
                print(f"[Orchestrator] Initializing {name} collector...")
                self.collectors[name] = cls(self.config, self.state)

    def _check_supabase(self) -> bool:
        """Verify Supabase connection and setup tables."""
        print("\n[Orchestrator] Checking Supabase connection...")
        if not self.supabase.health_check():
            print("[Orchestrator] FATAL: Cannot connect to Supabase. Check config.yaml credentials.")
            return False
        self.supabase.setup_tables()
        return True

    def _init_compiler(self):
        """Initialize compiler with Supabase."""
        self.compiler = DataCompiler(
            supabase=self.supabase,
            output_dir=self.config.get("output.dir", "./output/compiled"),
            fmt=self.config.get("output.format", "parquet"),
            local_backup=self.config.get("output.local_backup", True),
            batch_size=self.config.get("output.batch_size", 5000)
        )

    def run_init(self):
        """Initial big pull - ignores watermarks, collects everything."""
        print("=" * 65)
        print("  RESONANCE DATA AGENT - INITIAL PULL")
        print("  Collecting baseline dataset (20,000-50,000 records)")
        print("=" * 65)

        if not self._check_supabase():
            return
        self._init_compiler()

        total = 0
        for name, collector in self.collectors.items():
            print(f"\n[Orchestrator] >>> INIT: {name.upper()}")
            if not collector.health_check():
                print(f"  [Orchestrator] {name} SKIPPED")
                continue

            start = time.time()
            for batch in collector.collect(init_mode=True):
                self.compiler.add(batch)

            elapsed = time.time() - start
            stats = collector.get_stats()
            total += stats["records"]
            print(f"  [Orchestrator] {name} DONE in {elapsed:.1f}s | Records: {stats['records']}")

        self.compiler.finalize()
        print(f"\n[Orchestrator] INIT COMPLETE. Total baseline records: {total}")
        print("=" * 65)

    def run_incremental(self, collector_name: str = None):
        """One incremental run - only new data since last watermark."""
        if not self._check_supabase():
            return
        self._init_compiler()

        targets = {collector_name: self.collectors[collector_name]} if collector_name else self.collectors

        for name, collector in targets.items():
            print(f"\n[Orchestrator] >>> INCREMENTAL: {name.upper()}")
            if not collector.health_check():
                continue

            start = time.time()
            for batch in collector.collect(init_mode=False):
                self.compiler.add(batch)

            elapsed = time.time() - start
            stats = collector.get_stats()
            print(f"  [Orchestrator] {name} DONE in {elapsed:.1f}s | New records: {stats.get('new_records', 0)}")

        self.compiler.finalize()

    def run_live(self):
        """Start 24/7 live collection with scheduler."""
        print("=" * 65)
        print("  RESONANCE DATA AGENT - LIVE MODE (24/7)")
        print("  Press Ctrl+C to stop")
        print("=" * 65)

        if not self._check_supabase():
            return
        self._init_compiler()

        scheduler = LiveScheduler()

        # Register jobs with intervals from config
        if "reddit" in self.collectors:
            interval = self.config.get("scheduler.reddit_interval_minutes", 15)
            scheduler.add_job(
                lambda: self._run_single("reddit"),
                interval, "reddit"
            )

        if "youtube" in self.collectors:
            interval = self.config.get("scheduler.youtube_interval_minutes", 30)
            scheduler.add_job(
                lambda: self._run_single("youtube"),
                interval, "youtube"
            )

        if "kaggle" in self.collectors:
            interval = self.config.get("scheduler.kaggle_interval_hours", 24)
            scheduler.add_hourly_job(
                lambda: self._run_single("kaggle"),
                interval, "kaggle"
            )

        if "huggingface" in self.collectors:
            interval = self.config.get("scheduler.huggingface_interval_hours", 24)
            scheduler.add_hourly_job(
                lambda: self._run_single("huggingface"),
                interval, "huggingface"
            )

        if "scraper" in self.collectors:
            interval = self.config.get("scheduler.scraper_interval_hours", 6)
            scheduler.add_hourly_job(
                lambda: self._run_single("scraper"),
                interval, "scraper"
            )

        scheduler.run()

    def _run_single(self, name: str):
        """Run a single collector incrementally."""
        collector = self.collectors.get(name)
        if not collector:
            return

        if not collector.health_check():
            return

        for batch in collector.collect(init_mode=False):
            self.compiler.add(batch)

        self.compiler.finalize()

        # Print current DB size
        total = self.supabase.get_total_records()
        print(f"  [Live] Database now has {total:,} total records")
