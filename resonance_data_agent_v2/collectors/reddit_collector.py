"""Reddit collector with incremental support via Arctic Shift API."""
import requests
import time
import uuid
from datetime import datetime
from collectors.base import BaseCollector
from core.schema import UnifiedRecord


class RedditCollector(BaseCollector):
    name = "reddit"

    def __init__(self, config, state_manager=None):
        super().__init__(config, state_manager)
        self.base_url = "https://arctic-shift.photon-reddit.com/api"
        self.subreddits = config.get("reddit.subreddits", ["SkincareAddiction"])
        self.posts_per = config.get("reddit.posts_per_subreddit", 500)
        self.comments_per = config.get("reddit.comments_per_post", 10)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "ResonanceDataAgent/1.0"

    def health_check(self):
        try:
            r = self.session.get(f"{self.base_url}/status", timeout=10)
            return r.status_code == 200
        except Exception as e:
            print(f"  [Reddit] Health check failed: {e}")
            return False

    def _fetch_posts(self, sub, after=None, before=None):
        url = f"{self.base_url}/posts/search"
        params = {"subreddit": sub, "sort": "created_utc", "order": "desc", "limit": 100}
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        r = self.session.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _fetch_comments(self, post_id):
        url = f"{self.base_url}/comments/search"
        params = {"link_id": post_id, "limit": self.comments_per}
        try:
            r = self.session.get(url, params=params, timeout=30)
            return r.json().get("data", [])
        except:
            return []

    def _make_post(self, p, sub):
        created = datetime.utcfromtimestamp(p.get("created_utc", 0)) if p.get("created_utc") else None
        return UnifiedRecord(
            record_id=f"rd_post_{p.get('id', uuid.uuid4().hex)}",
            source="reddit", content_type="post",
            author_id=p.get("author", "unknown"), author_name=p.get("author", "unknown"),
            title=p.get("title", ""), text=p.get("selftext", ""),
            url=p.get("url", ""), platform="reddit", channel=sub,
            thread_id=p.get("id"), likes=p.get("score"), comments=p.get("num_comments"),
            created_at=created,
            metadata={"permalink": p.get("permalink"), "is_self": p.get("is_self")}
        )

    def _make_comment(self, c, sub, post_id):
        created = datetime.utcfromtimestamp(c.get("created_utc", 0)) if c.get("created_utc") else None
        return UnifiedRecord(
            record_id=f"rd_cmt_{c.get('id', uuid.uuid4().hex)}",
            source="reddit", content_type="comment",
            author_id=c.get("author", "unknown"), author_name=c.get("author", "unknown"),
            text=c.get("body", ""), platform="reddit", channel=sub,
            thread_id=post_id, parent_id=c.get("parent_id"), likes=c.get("score"),
            created_at=created,
            metadata={"permalink": c.get("permalink")}
        )

    def collect(self, init_mode=False):
        batch = []
        for sub in self.subreddits:
            watermark = None if init_mode else self._get_watermark(sub)

            if init_mode:
                print(f"  [Reddit] INIT: Collecting r/{sub} (ignoring watermarks)...")
            else:
                if watermark:
                    print(f"  [Reddit] INCREMENTAL: r/{sub} since timestamp {watermark}")
                else:
                    print(f"  [Reddit] INCREMENTAL: r/{sub} (no watermark, doing full pull)")

            collected = 0
            new_records = 0
            after = None
            before = None
            latest_timestamp = watermark
            latest_record_id = ""

            # For incremental, we need to fetch posts BEFORE the watermark
            # (since Arctic Shift returns newest first, and we want everything NEWER than watermark)
            # Actually Arctic Shift 'after' means posts created AFTER this timestamp
            # So for incremental: after=watermark
            if not init_mode and watermark:
                after = watermark

            while collected < self.posts_per:
                try:
                    data = self._fetch_posts(sub, after, before)
                    posts = data.get("data", [])
                    if not posts:
                        break

                    for p in posts:
                        # Skip if we already have this (safety check)
                        if not init_mode and watermark:
                            post_time = str(p.get("created_utc", ""))
                            if post_time and post_time <= watermark:
                                continue

                        batch.append(self._make_post(p, sub))
                        self.stats["records"] += 1
                        collected += 1
                        new_records += 1

                        # Track latest for watermark
                        if p.get("created_utc"):
                            ts = str(p["created_utc"])
                            if not latest_timestamp or ts > latest_timestamp:
                                latest_timestamp = ts
                                latest_record_id = p.get("id", "")

                        if p.get("num_comments", 0) > 0:
                            for c in self._fetch_comments(p["id"]):
                                batch.append(self._make_comment(c, sub, p["id"]))
                                self.stats["records"] += 1
                                new_records += 1

                        if len(batch) >= 500:
                            self.stats["batches"] += 1
                            yield batch
                            batch = []

                    # Pagination: for init mode, paginate backwards through history
                    # For incremental, paginate forward from watermark
                    if init_mode:
                        before = posts[-1].get("created_utc")
                    else:
                        after = posts[-1].get("created_utc")

                    time.sleep(0.5)

                except Exception as e:
                    print(f"  [Reddit] Error in r/{sub}: {e}")
                    self.stats["errors"] += 1
                    break

            # Update watermark for this subreddit
            if latest_timestamp:
                self._set_watermark(sub, latest_timestamp, latest_record_id, new_records)
                self.stats["new_records"] += new_records

            print(f"  [Reddit] r/{sub}: {collected} posts | New: {new_records}")

        if batch:
            self.stats["batches"] += 1
            yield batch
