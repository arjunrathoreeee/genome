"""Hugging Face collector with incremental support."""
import uuid
from collectors.base import BaseCollector
from core.schema import UnifiedRecord


class HuggingFaceCollector(BaseCollector):
    name = "huggingface"

    def __init__(self, config, state_manager=None):
        super().__init__(config, state_manager)
        self.datasets = config.get("huggingface.datasets", [])

    def health_check(self):
        try:
            from datasets import load_dataset
            return True
        except ImportError:
            print("  [HF] datasets library not installed. Run: pip install datasets")
            return False

    def _load(self, ref):
        from datasets import load_dataset
        print(f"  [HF] Loading {ref}...")
        ds = load_dataset(ref, trust_remote_code=True)
        print(f"  [HF]   Loaded")
        return ds

    def _get_dataset_version(self, ref):
        """Get dataset revision/hash for change detection."""
        try:
            from datasets import load_dataset_builder
            builder = load_dataset_builder(ref)
            # Use config name + features as proxy for version
            return str(builder.info.version) if builder.info.version else "unknown"
        except:
            return "unknown"

    def _norm_marketing(self, ds):
        batch = []
        split = "train" if "train" in ds else list(ds.keys())[0]
        for item in ds[split]:
            batch.append(UnifiedRecord(
                record_id=f"hf_mkt_{uuid.uuid4().hex}", source="huggingface", content_type="campaign",
                author_id="brand", author_name="brand",
                title=str(item.get("brand", "")),
                text=f"Target: {item.get('target_audience', '')} | Goals: {item.get('goals', '')}",
                platform="unknown",
                metadata={"dataset": "marketing_social_media", "strategy": item.get("proposed_strategy")}
            ))
            self.stats["records"] += 1
            if len(batch) >= 100:
                self.stats["batches"] += 1
                yield batch
                batch = []
        if batch:
            self.stats["batches"] += 1
            yield batch

    def _norm_reddit(self, ds):
        batch = []
        split = "train" if "train" in ds else list(ds.keys())[0]
        for item in ds[split]:
            batch.append(UnifiedRecord(
                record_id=f"hf_rd_{uuid.uuid4().hex}", source="huggingface", content_type="comment",
                author_id=str(item.get("author", "")), author_name=str(item.get("author", "")),
                text=str(item.get("body", "")), platform="reddit",
                channel=str(item.get("subreddit", "")), thread_id=str(item.get("post_id", "")),
                likes=item.get("score"),
                metadata={"dataset": "reddit_comments", "subreddit": item.get("subreddit")}
            ))
            self.stats["records"] += 1
            if len(batch) >= 1000:
                self.stats["batches"] += 1
                yield batch
                batch = []
        if batch:
            self.stats["batches"] += 1
            yield batch

    def _norm_generic(self, ds, ref):
        batch = []
        split = "train" if "train" in ds else list(ds.keys())[0]
        sample = ds[split][0] if len(ds[split]) > 0 else {}
        text_key = None
        for k in sample.keys():
            if any(x in k.lower() for x in ["text", "content", "body"]):
                text_key = k
                break
        if not text_key:
            text_key = list(sample.keys())[0] if sample else "text"
        for item in ds[split]:
            batch.append(UnifiedRecord(
                record_id=f"hf_gen_{uuid.uuid4().hex}", source="huggingface", content_type="post",
                author_id="unknown", author_name="unknown",
                text=str(item.get(text_key, "")), platform="unknown",
                metadata={"dataset": ref, "keys": list(item.keys())}
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
        for ref in self.datasets:
            # Check version for incremental
            current_version = self._get_dataset_version(ref)
            last_version = None if init_mode else self._get_watermark(ref)

            if not init_mode and last_version == current_version:
                print(f"  [HF] {ref} unchanged (version: {current_version}), skipping")
                continue

            if init_mode:
                print(f"  [HF] INIT: Loading {ref}")
            else:
                print(f"  [HF] INCREMENTAL: Loading {ref} (version: {current_version})")

            try:
                ds = self._load(ref)

                if "marketing" in ref.lower():
                    yield from self._norm_marketing(ds)
                elif "reddit" in ref.lower():
                    yield from self._norm_reddit(ds)
                else:
                    yield from self._norm_generic(ds, ref)

                # Update watermark with version
                self._set_watermark(ref, current_version, current_version, self.stats["records"])

            except Exception as e:
                print(f"  [HF] Error with {ref}: {e}")
                self.stats["errors"] += 1
