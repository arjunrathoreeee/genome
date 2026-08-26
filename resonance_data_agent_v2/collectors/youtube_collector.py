"""YouTube collector with incremental support."""
import uuid
from datetime import datetime
from collectors.base import BaseCollector
from core.schema import UnifiedRecord


class YouTubeCollector(BaseCollector):
    name = "youtube"

    def __init__(self, config, state_manager=None):
        super().__init__(config, state_manager)
        self.api_key = config.get_api_key("youtube")
        self.channels = config.get("youtube.channels", [])
        self.max_videos = config.get("youtube.max_videos_per_channel", 20)
        self.max_comments = config.get("youtube.max_comments_per_video", 100)
        self.base = "https://www.googleapis.com/youtube/v3"

    def health_check(self):
        if not self.api_key:
            print("  [YouTube] No API key. Set youtube_api_key in config.yaml or YOUTUBE_API_KEY env var.")
            return False
        import requests
        try:
            r = requests.get(f"{self.base}/search", params={"part": "snippet", "q": "test", "key": self.api_key, "maxResults": 1}, timeout=10)
            return r.status_code == 200
        except Exception as e:
            print(f"  [YouTube] Health check failed: {e}")
            return False

    def _get(self, endpoint, params):
        import requests
        params["key"] = self.api_key
        r = requests.get(f"{self.base}/{endpoint}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _get_videos(self, channel_id, published_after=None):
        """Get videos. If published_after provided, only get videos after that date."""
        ch = self._get("channels", {"part": "contentDetails", "id": channel_id})
        items = ch.get("items", [])
        if not items:
            return []

        playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        videos = []
        token = None

        while len(videos) < self.max_videos:
            params = {
                "part": "snippet,contentDetails,statistics",
                "playlistId": playlist,
                "maxResults": min(50, self.max_videos - len(videos))
            }
            if published_after:
                # Note: playlistItems doesn't support publishedAfter
                # We filter after fetching
                pass
            if token:
                params["pageToken"] = token

            data = self._get("playlistItems", params)
            for item in data.get("items", []):
                vid = item["contentDetails"]["videoId"]
                vd = self._get("videos", {"part": "snippet,statistics", "id": vid})
                if vd.get("items"):
                    v = vd["items"][0]
                    # Filter by publishedAfter if specified
                    if published_after:
                        pub = v["snippet"].get("publishedAt", "")
                        if pub and pub <= published_after:
                            continue
                    videos.append(v)

            token = data.get("nextPageToken")
            if not token or len(videos) >= self.max_videos:
                break

        return videos[:self.max_videos]

    def _get_comments(self, video_id):
        comments = []
        token = None
        while len(comments) < self.max_comments:
            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": min(100, self.max_comments - len(comments)),
                "order": "time"  # Newest first for incremental
            }
            if token:
                params["pageToken"] = token
            try:
                data = self._get("commentThreads", params)
                for item in data.get("items", []):
                    s = item["snippet"]["topLevelComment"]["snippet"]
                    comments.append({
                        "id": item["id"], "author": s["authorDisplayName"],
                        "text": s["textDisplay"], "likes": s.get("likeCount", 0),
                        "published": s["publishedAt"]
                    })
                token = data.get("nextPageToken")
                if not token:
                    break
            except:
                break
        return comments

    def _video_record(self, v, channel_id):
        s = v["snippet"]
        stats = v.get("statistics", {})
        try:
            created = datetime.fromisoformat(s.get("publishedAt", "").replace("Z", "+00:00"))
        except:
            created = None
        return UnifiedRecord(
            record_id=f"yt_vid_{v['id']}", source="youtube", content_type="video",
            author_id=channel_id, author_name=s.get("channelTitle", ""),
            title=s.get("title", ""), text=s.get("description", ""),
            url=f"https://youtube.com/watch?v={v['id']}", platform="youtube",
            channel=s.get("channelTitle"), likes=int(stats.get("likeCount", 0) or 0),
            comments=int(stats.get("commentCount", 0) or 0),
            views=int(stats.get("viewCount", 0) or 0),
            created_at=created,
            metadata={"tags": s.get("tags", []), "category_id": s.get("categoryId")}
        )

    def _comment_record(self, c, video_id, channel):
        try:
            created = datetime.fromisoformat(c.get("published", "").replace("Z", "+00:00"))
        except:
            created = None
        return UnifiedRecord(
            record_id=f"yt_cmt_{c['id']}", source="youtube", content_type="comment",
            author_id=c["author"], author_name=c["author"], text=c["text"],
            platform="youtube", channel=channel, thread_id=video_id, parent_id=video_id,
            likes=c.get("likes"), created_at=created, metadata={}
        )

    def collect(self, init_mode=False):
        batch = []
        for ch in self.channels:
            watermark = None if init_mode else self._get_watermark(ch)

            if init_mode:
                print(f"  [YouTube] INIT: Channel {ch}")
            else:
                if watermark:
                    print(f"  [YouTube] INCREMENTAL: Channel {ch} since {watermark}")
                else:
                    print(f"  [YouTube] INCREMENTAL: Channel {ch} (no watermark)")

            try:
                videos = self._get_videos(ch, published_after=watermark)
                print(f"  [YouTube]   Found {len(videos)} new videos")

                new_records = 0
                latest_timestamp = watermark
                latest_record_id = ""

                for v in videos:
                    batch.append(self._video_record(v, ch))
                    self.stats["records"] += 1
                    new_records += 1

                    # Track latest
                    pub = v["snippet"].get("publishedAt", "")
                    if pub and (not latest_timestamp or pub > latest_timestamp):
                        latest_timestamp = pub
                        latest_record_id = v["id"]

                    # Get comments
                    for c in self._get_comments(v["id"]):
                        batch.append(self._comment_record(c, v["id"], v["snippet"].get("channelTitle", "")))
                        self.stats["records"] += 1
                        new_records += 1

                    if len(batch) >= 500:
                        self.stats["batches"] += 1
                        yield batch
                        batch = []

                # Update watermark
                if latest_timestamp and latest_timestamp != watermark:
                    self._set_watermark(ch, latest_timestamp, latest_record_id, new_records)
                    self.stats["new_records"] += new_records

            except Exception as e:
                print(f"  [YouTube] Error with channel {ch}: {e}")
                self.stats["errors"] += 1

        if batch:
            self.stats["batches"] += 1
            yield batch
