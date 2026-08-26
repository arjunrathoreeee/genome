"""Lightweight web scraper for public pages."""
import uuid
import time
from collectors.base import BaseCollector
from core.schema import UnifiedRecord


class ScraperCollector(BaseCollector):
    name = "scraper"

    def __init__(self, config, state_manager=None):
        super().__init__(config, state_manager)
        self.targets = config.get("scraper.targets", [])

    def health_check(self):
        try:
            import requests
            from bs4 import BeautifulSoup
            return True
        except ImportError:
            print("  [Scraper] requests or beautifulsoup4 not installed.")
            return False

    def _scrape(self, url, platform):
        import requests
        from bs4 import BeautifulSoup
        records = []
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            meta = soup.find("meta", property="og:description")
            text = meta["content"] if meta else ""
            title_meta = soup.find("meta", property="og:title")
            title = title_meta["content"] if title_meta else ""
            records.append(UnifiedRecord(
                record_id=f"scrape_{uuid.uuid4().hex}", source="scraper", content_type="profile",
                author_id=url.split("/")[-2] if "/" in url else "unknown",
                author_name=url.split("/")[-2] if "/" in url else "unknown",
                title=title, text=text, url=url, platform=platform,
                metadata={"scrape_method": "og_meta"}
            ))
            self.stats["records"] += 1
        except Exception as e:
            print(f"  [Scraper] Failed {url}: {e}")
            self.stats["errors"] += 1
        return records

    def collect(self, init_mode=False):
        batch = []
        for t in self.targets:
            url = t.get("url", "")
            platform = t.get("platform", "")
            if not url:
                continue
            print(f"  [Scraper] Scraping {platform}: {url}...")
            batch.extend(self._scrape(url, platform))
            time.sleep(2)
            if len(batch) >= 50:
                self.stats["batches"] += 1
                yield batch
                batch = []
        if batch:
            self.stats["batches"] += 1
            yield batch
