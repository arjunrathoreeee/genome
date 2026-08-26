#!/usr/bin/env python3
"""Resonance Data Agent v2 - Incremental + Live + Supabase

Usage:
    python main.py --init          # First big pull (20k-50k records)
    python main.py --live          # 24/7 incremental collection
    python main.py --incremental   # One incremental run (all sources)
    python main.py --reset         # Reset all watermarks and start fresh
    python main.py --status        # Show current database status

Setup:
    1. pip install -r requirements.txt
    2. Edit config.yaml - add Supabase credentials + YouTube API key
    3. Run sql/setup.sql in your Supabase SQL Editor
    4. python main.py --init
    5. python main.py --live
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.orchestrator import Orchestrator
from core.config import Config
from core.supabase_client import SupabaseClient


def main():
    parser = argparse.ArgumentParser(description="Resonance Data Agent v2")
    parser.add_argument("--init", action="store_true", help="Initial big pull (ignores watermarks)")
    parser.add_argument("--live", action="store_true", help="Start 24/7 live incremental collection")
    parser.add_argument("--incremental", action="store_true", help="One incremental run")
    parser.add_argument("--reset", action="store_true", help="Reset all watermarks")
    parser.add_argument("--status", action="store_true", help="Show database status")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    args = parser.parse_args()

    config_path = args.config
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    # Show status and exit
    if args.status:
        config = Config(config_path)
        sb = SupabaseClient(config)
        if sb.health_check():
            total = sb.get_total_records()
            print(f"\n  Database status: {total:,} total records in raw_data")
        else:
            print("\n  Cannot connect to Supabase. Check credentials.")
        return

    # Reset watermarks
    if args.reset:
        config = Config(config_path)
        sb = SupabaseClient(config)
        if sb.health_check():
            # Reset local state
            if os.path.exists(".state.json"):
                os.remove(".state.json")
                print("  Local state file removed.")
            print("  Watermarks reset. Run --init to do a fresh pull.")
        return

    # Main orchestrator
    agent = Orchestrator(config_path)

    if args.init:
        agent.run_init()
    elif args.live:
        agent.run_live()
    elif args.incremental:
        agent.run_incremental()
    else:
        print("""
Resonance Data Agent v2
========================

No command specified. Choose one:

  python main.py --init        # First-time big data pull
  python main.py --live        # Start 24/7 live collection
  python main.py --incremental # One incremental run
  python main.py --status      # Check database record count
  python main.py --reset       # Reset watermarks

See README.md for full setup instructions.
        """)


if __name__ == "__main__":
    main()
