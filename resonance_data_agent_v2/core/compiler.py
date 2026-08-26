"""Compiler - batches records and writes to Supabase (+ optional local backup)."""
import os
import json
from datetime import datetime
from typing import List
import pandas as pd
from core.schema import UnifiedRecord
from core.supabase_client import SupabaseClient


class DataCompiler:
    """Compiles batches of records into Supabase + optional local files."""

    def __init__(self, supabase: SupabaseClient, output_dir="./output/compiled", 
                 fmt="parquet", local_backup=True, batch_size=5000):
        self.supabase = supabase
        self.output_dir = output_dir
        self.format = fmt
        self.local_backup = local_backup
        self.batch_size = batch_size
        self.buffer = []
        self.file_count = 0
        self.total_inserted = 0

        if local_backup:
            os.makedirs(output_dir, exist_ok=True)

    def add(self, records: List[UnifiedRecord]):
        """Add records to buffer. Flush when batch_size reached."""
        self.buffer.extend(records)
        while len(self.buffer) >= self.batch_size:
            self._flush(self.buffer[:self.batch_size])
            self.buffer = self.buffer[self.batch_size:]

    def _flush(self, records: List[UnifiedRecord]):
        """Flush a batch to Supabase and optionally local."""
        if not records:
            return

        # 1. Insert to Supabase
        inserted = self.supabase.insert_records(records)
        self.total_inserted += inserted

        # 2. Optional local backup
        if self.local_backup:
            self._write_local(records)

        print(f"  [Compiler] Flushed {len(records)} records (DB: {inserted} inserted)")

    def _write_local(self, records: List[UnifiedRecord]):
        """Write batch to local file as backup."""
        df = pd.DataFrame([r.to_dict() for r in records])
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"resonance_{ts}_part{self.file_count:04d}"

        if self.format == "parquet":
            path = os.path.join(self.output_dir, f"{name}.parquet")
            df.to_parquet(path, index=False)
        elif self.format == "csv":
            path = os.path.join(self.output_dir, f"{name}.csv")
            df.to_csv(path, index=False, encoding="utf-8")
        else:
            path = os.path.join(self.output_dir, f"{name}.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r.to_dict()) + "\n")

        self.file_count += 1

    def finalize(self):
        """Flush remaining buffer."""
        if self.buffer:
            self._flush(self.buffer)
            self.buffer = []

        total_db = self.supabase.get_total_records()
        print(f"\n  [Compiler] FINALIZED")
        print(f"    This run inserted: {self.total_inserted}")
        print(f"    Total in database: {total_db}")
        if self.local_backup:
            print(f"    Local backup files: {self.file_count}")
