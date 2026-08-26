"""Supabase client for data storage and retrieval.

Supports two modes:
  1. Direct PostgreSQL (psycopg2) - FAST bulk inserts
  2. REST API (supabase-py) - Simpler, no connection pooling needed
"""
import os
import json
from typing import List, Dict, Any, Optional
from core.schema import UnifiedRecord, RAW_DATA_TABLE_SQL, STATE_TABLE_SQL


class SupabaseClient:
    """Handles all Supabase database operations."""

    def __init__(self, config):
        self.creds = config.get_supabase_creds()
        self.use_direct = self.creds["use_direct_postgres"]
        self._pg_conn = None
        self._sb_client = None
        self._connected = False

    def health_check(self) -> bool:
        """Verify Supabase credentials work."""
        if not self.creds["project_url"] or not self.creds["service_role_key"]:
            print("  [Supabase] ERROR: Missing project_url or service_role_key in config.yaml")
            return False
        try:
            if self.use_direct and self.creds["db_password"]:
                return self._check_postgres()
            else:
                return self._check_rest()
        except Exception as e:
            print(f"  [Supabase] Connection failed: {e}")
            return False

    def _check_postgres(self) -> bool:
        import psycopg2
        conn = psycopg2.connect(
            host=self.creds["db_host"],
            port=self.creds["db_port"],
            dbname=self.creds["db_name"],
            user=self.creds["db_user"],
            password=self.creds["db_password"],
            sslmode="require"
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        print("  [Supabase] Direct PostgreSQL connection: OK")
        return True

    def _check_rest(self) -> bool:
        from supabase import create_client
        sb = create_client(self.creds["project_url"], self.creds["service_role_key"])
        sb.table("collection_state").select("*").limit(1).execute()
        print("  [Supabase] REST API connection: OK")
        return True

    def _get_pg_conn(self):
        """Lazy-init PostgreSQL connection."""
        if self._pg_conn is None or self._pg_conn.closed:
            import psycopg2
            self._pg_conn = psycopg2.connect(
                host=self.creds["db_host"],
                port=self.creds["db_port"],
                dbname=self.creds["db_name"],
                user=self.creds["db_user"],
                password=self.creds["db_password"],
                sslmode="require"
            )
        return self._pg_conn

    def _get_sb_client(self):
        """Lazy-init Supabase REST client."""
        if self._sb_client is None:
            from supabase import create_client
            self._sb_client = create_client(
                self.creds["project_url"],
                self.creds["service_role_key"]
            )
        return self._sb_client

    def setup_tables(self):
        """Create tables if they don't exist. Run this once."""
        print("  [Supabase] Setting up tables...")
        if self.use_direct and self.creds["db_password"]:
            conn = self._get_pg_conn()
            cur = conn.cursor()
            cur.execute(RAW_DATA_TABLE_SQL)
            cur.execute(STATE_TABLE_SQL)
            conn.commit()
            cur.close()
        else:
            sb = self._get_sb_client()
            # Tables must be created via Supabase SQL Editor or migrations
            # We just verify they exist
            try:
                sb.table("raw_data").select("id").limit(1).execute()
                sb.table("collection_state").select("*").limit(1).execute()
            except Exception as e:
                print(f"  [Supabase] WARNING: Tables may not exist. Run sql/setup.sql in Supabase SQL Editor.")
                print(f"    Error: {e}")
                return False
        print("  [Supabase] Tables ready")
        return True

    def insert_records(self, records: List[UnifiedRecord]) -> int:
        """Insert batch of records. Returns count inserted."""
        if not records:
            return 0

        if self.use_direct and self.creds["db_password"]:
            return self._insert_via_postgres(records)
        else:
            return self._insert_via_rest(records)

    def _insert_via_postgres(self, records: List[UnifiedRecord]) -> int:
        """Bulk insert using psycopg2 execute_values (FAST)."""
        import psycopg2
        from psycopg2.extras import execute_values

        conn = self._get_pg_conn()
        cur = conn.cursor()

        tuples = [r.to_db_tuple() for r in records]
        query = """
            INSERT INTO raw_data (
                record_id, source, content_type, author_id, author_name, author_handle,
                title, text, url, platform, channel, thread_id, parent_id,
                likes, comments, shares, views, engagement_rate,
                created_at, collected_at, metadata, subculture_tags, value_keywords,
                sentiment, resonance_score
            ) VALUES %s
            ON CONFLICT (record_id) DO NOTHING
        """

        try:
            execute_values(cur, query, tuples, page_size=1000)
            conn.commit()
            return len(tuples)
        except Exception as e:
            conn.rollback()
            print(f"  [Supabase] PG insert error: {e}")
            return 0
        finally:
            cur.close()

    def _insert_via_rest(self, records: List[UnifiedRecord]) -> int:
        """Insert via Supabase REST API (slower, no persistent conn)."""
        sb = self._get_sb_client()
        batch_size = 100
        inserted = 0

        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            rows = [r.to_dict() for r in batch]
            try:
                sb.table("raw_data").insert(rows, upsert="{\"on_conflict\":\"record_id\"}").execute()
                inserted += len(batch)
            except Exception as e:
                print(f"  [Supabase] REST insert error (batch {i}): {e}")

        return inserted

    def get_state(self, source: str, sub_source: str) -> Optional[Dict[str, Any]]:
        """Get watermark state for a source+sub_source."""
        if self.use_direct and self.creds["db_password"]:
            conn = self._get_pg_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT last_timestamp, last_record_id, record_count FROM collection_state WHERE source=%s AND sub_source=%s",
                (source, sub_source)
            )
            row = cur.fetchone()
            cur.close()
            if row:
                return {"last_timestamp": row[0], "last_record_id": row[1], "record_count": row[2]}
            return None
        else:
            sb = self._get_sb_client()
            resp = sb.table("collection_state").select("*").eq("source", source).eq("sub_source", sub_source).execute()
            if resp.data:
                return resp.data[0]
            return None

    def set_state(self, source: str, sub_source: str, last_timestamp: str, last_record_id: str, record_count: int = 0):
        """Update or insert watermark state."""
        if self.use_direct and self.creds["db_password"]:
            conn = self._get_pg_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO collection_state (source, sub_source, last_timestamp, last_record_id, record_count, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (source, sub_source)
                DO UPDATE SET last_timestamp=EXCLUDED.last_timestamp, last_record_id=EXCLUDED.last_record_id,
                              record_count=collection_state.record_count + EXCLUDED.record_count, updated_at=NOW()
            """, (source, sub_source, last_timestamp, last_record_id, record_count))
            conn.commit()
            cur.close()
        else:
            sb = self._get_sb_client()
            sb.table("collection_state").upsert({
                "source": source, "sub_source": sub_source,
                "last_timestamp": last_timestamp, "last_record_id": last_record_id,
                "record_count": record_count, "updated_at": "now()"
            }).execute()

    def get_total_records(self) -> int:
        """Get total record count in raw_data."""
        if self.use_direct and self.creds["db_password"]:
            conn = self._get_pg_conn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM raw_data")
            count = cur.fetchone()[0]
            cur.close()
            return count
        else:
            sb = self._get_sb_client()
            resp = sb.table("raw_data").select("id", count="exact").limit(0).execute()
            return resp.count or 0

    def close(self):
        """Close connections."""
        if self._pg_conn:
            self._pg_conn.close()
            self._pg_conn = None
