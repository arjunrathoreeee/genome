"""Kaggle collector with incremental support (checks for updates)."""
import os
import uuid
import hashlib
from collectors.base import BaseCollector
from core.schema import UnifiedRecord


class KaggleCollector(BaseCollector):
    name = "kaggle"

    def __init__(self, config, state_manager=None):
        super().__init__(config, state_manager)
        self.datasets = config.get("kaggle.datasets", [])
        self.download_dir = os.path.join(base, "output", "kaggle")
        os.makedirs(self.download_dir, exist_ok=True)

    def health_check(self):
        try:
            import kagglehub
            return True
        except ImportError:
            print("  [Kaggle] kagglehub not installed. Run: pip install kagglehub")
            return False

    def _download(self, ref):
        import kagglehub
        print(f"  [Kaggle] Downloading {ref}...")
        path = kagglehub.dataset_download(ref)
        print(f"  [Kaggle]   -> {path}")
        return path

    def _find_csv(self, path):
        csvs = []
        for root, _, files in os.walk(path):
            for f in files:
                if f.endswith(".csv"):
                    csvs.append(os.path.join(root, f))
        return csvs

    def _file_hash(self, path):
        """Get MD5 hash of file to detect changes."""
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _normalize_youtube(self, df):
        import pandas as pd
        batch = []
        for _, row in df.iterrows():
            batch.append(UnifiedRecord(
                record_id=f"kg_yt_{uuid.uuid4().hex}", source="kaggle", content_type="video",
                author_id=str(row.get("channel_title", "")), author_name=str(row.get("channel_title", "")),
                title=str(row.get("title", "")), text=str(row.get("description", "")),
                url=str(row.get("video_id", "")), platform="youtube",
                likes=row.get("likes"), comments=row.get("comment_count"), views=row.get("views"),
                metadata={"tags": str(row.get("tags", "")).split("|") if pd.notna(row.get("tags")) else [], "dataset": "youtube_trending"}
            ))
            self.stats["records"] += 1
            if len(batch) >= 1000:
                self.stats["batches"] += 1
                yield batch
                batch = []
        if batch:
            self.stats["batches"] += 1
            yield batch

    def _normalize_amazon(self, df):
        batch = []
        for _, row in df.iterrows():
            batch.append(UnifiedRecord(
                record_id=f"kg_amz_{row.get('Id', uuid.uuid4().hex)}", source="kaggle", content_type="review",
                author_id=str(row.get("UserId", "")), author_name=str(row.get("ProfileName", "")),
                title=str(row.get("Summary", "")), text=str(row.get("Text", "")),
                platform="amazon", channel=str(row.get("ProductId", "")),
                likes=row.get("HelpfulnessNumerator"), views=row.get("HelpfulnessDenominator"),
                metadata={"score": row.get("Score"), "product_id": str(row.get("ProductId", "")), "dataset": "amazon_reviews"}
            ))
            self.stats["records"] += 1
            if len(batch) >= 1000:
                self.stats["batches"] += 1
                yield batch
                batch = []
        if batch:
            self.stats["batches"] += 1
            yield batch

    def _normalize_generic(self, df, name):
        batch = []
        text_col = None
        for c in df.columns:
            if any(x in c.lower() for x in ["text", "content", "body", "review"]):
                text_col = c
                break
        if not text_col:
            text_col = df.columns[0]
        for _, row in df.iterrows():
            batch.append(UnifiedRecord(
                record_id=f"kg_gen_{uuid.uuid4().hex}", source="kaggle", content_type="post",
                author_id="unknown", author_name="unknown",
                text=str(row.get(text_col, "")), platform="unknown",
                metadata={"dataset": name, "columns": list(row.index)}
            ))
            self.stats["records"] += 1
            if len(batch) >= 1000:
                self.stats["batches"] += 1
                yield batch
                batch = []
        if batch:
            self.stats["batches"] += 1
            yield batch

    def collect(self, init_mode=False):
        import pandas as pd

        for ref in self.datasets:
            # Check if dataset has changed since last pull
            if not init_mode:
                last_hash = self._get_watermark(ref)
                if last_hash:
                    print(f"  [Kaggle] Checking {ref} for updates...")
                    # We can't check hash without downloading, so we download and compare
                else:
                    print(f"  [Kaggle] No previous state for {ref}, doing full pull")

            try:
                path = self._download(ref)
                new_hash = None

                for csv in self._find_csv(path):
                    if not new_hash:
                        new_hash = self._file_hash(csv)

                    # Skip if unchanged (only in incremental mode)
                    if not init_mode:
                        last_hash = self._get_watermark(ref)
                        if last_hash == new_hash:
                            print(f"  [Kaggle] {ref} unchanged (hash: {new_hash}), skipping")
                            continue

                    print(f"  [Kaggle] Processing {csv}...")
                    df = pd.read_csv(csv, low_memory=False)

                    if "youtube" in ref.lower() or "trending" in ref.lower():
                        yield from self._normalize_youtube(df)
                    elif "amazon" in ref.lower():
                        yield from self._normalize_amazon(df)
                    else:
                        yield from self._normalize_generic(df, ref)

                # Update watermark with file hash
                if new_hash:
                    self._set_watermark(ref, new_hash, new_hash, self.stats["records"])

            except Exception as e:
                print(f"  [Kaggle] Error with {ref}: {e}")
                self.stats["errors"] += 1
