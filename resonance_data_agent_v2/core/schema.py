"""Unified data schema - every record looks the same regardless of source."""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import json


@dataclass
class UnifiedRecord:
    record_id: str
    source: str
    content_type: str
    author_id: str
    author_name: str
    author_handle: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    platform: str = ""
    channel: Optional[str] = None
    thread_id: Optional[str] = None
    parent_id: Optional[str] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    views: Optional[int] = None
    engagement_rate: Optional[float] = None
    created_at: Optional[datetime] = None
    collected_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    subculture_tags: List[str] = field(default_factory=list)
    value_keywords: List[str] = field(default_factory=list)
    sentiment: Optional[str] = None
    resonance_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "source": self.source,
            "content_type": self.content_type,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "author_handle": self.author_handle,
            "title": self.title,
            "text": self.text,
            "url": self.url,
            "platform": self.platform,
            "channel": self.channel,
            "thread_id": self.thread_id,
            "parent_id": self.parent_id,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "views": self.views,
            "engagement_rate": self.engagement_rate,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "collected_at": self.collected_at.isoformat(),
            "metadata": json.dumps(self.metadata) if self.metadata else "{}",
            "subculture_tags": json.dumps(self.subculture_tags) if self.subculture_tags else "[]",
            "value_keywords": json.dumps(self.value_keywords) if self.value_keywords else "[]",
            "sentiment": self.sentiment,
            "resonance_score": self.resonance_score,
        }

    def to_db_tuple(self):
        """Return as tuple for psycopg2 execute_values."""
        return (
            self.record_id, self.source, self.content_type,
            self.author_id, self.author_name, self.author_handle,
            self.title, self.text, self.url,
            self.platform, self.channel, self.thread_id, self.parent_id,
            self.likes, self.comments, self.shares, self.views, self.engagement_rate,
            self.created_at, self.collected_at,
            json.dumps(self.metadata), json.dumps(self.subculture_tags), json.dumps(self.value_keywords),
            self.sentiment, self.resonance_score
        )


# SQL to create the raw_data table in Supabase
RAW_DATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS raw_data (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    record_id TEXT NOT NULL,
    source TEXT NOT NULL,
    content_type TEXT,
    author_id TEXT,
    author_name TEXT,
    author_handle TEXT,
    title TEXT,
    text TEXT,
    url TEXT,
    platform TEXT,
    channel TEXT,
    thread_id TEXT,
    parent_id TEXT,
    likes BIGINT,
    comments BIGINT,
    shares BIGINT,
    views BIGINT,
    engagement_rate FLOAT,
    created_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB,
    subculture_tags JSONB,
    value_keywords JSONB,
    sentiment TEXT,
    resonance_score FLOAT,
    inserted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_data(source);
CREATE INDEX IF NOT EXISTS idx_raw_platform ON raw_data(platform);
CREATE INDEX IF NOT EXISTS idx_raw_channel ON raw_data(channel);
CREATE INDEX IF NOT EXISTS idx_raw_author ON raw_data(author_id);
CREATE INDEX IF NOT EXISTS idx_raw_collected ON raw_data(collected_at);
CREATE INDEX IF NOT EXISTS idx_raw_record ON raw_data(record_id);
"""

STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS collection_state (
    source TEXT NOT NULL,
    sub_source TEXT NOT NULL,
    last_timestamp TEXT,
    last_record_id TEXT,
    record_count BIGINT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (source, sub_source)
);
"""
