"""State / watermark manager for incremental collection.

Tracks what has been collected so far, so we only pull NEW data.
State is stored BOTH in Supabase (primary) and local JSON (backup).
"""
import os
import json
from typing import Optional, Dict, Any
from core.supabase_client import SupabaseClient


class StateManager:
    """Manages collection watermarks/state."""

    LOCAL_STATE_FILE = ".state.json"

    def __init__(self, supabase: SupabaseClient):
        self.supabase = supabase
        self.local_state = self._load_local()

    def _load_local(self) -> Dict[str, Any]:
        """Load local state backup."""
        if os.path.exists(self.LOCAL_STATE_FILE):
            with open(self.LOCAL_STATE_FILE, "r") as f:
                return json.load(f)
        return {}

    def _save_local(self):
        """Save state to local file as backup."""
        with open(self.LOCAL_STATE_FILE, "w") as f:
            json.dump(self.local_state, f, indent=2)

    def get_watermark(self, source: str, sub_source: str) -> Optional[str]:
        """Get last timestamp/ID for a source. Returns None if never collected."""
        key = f"{source}:{sub_source}"

        # Try Supabase first
        try:
            state = self.supabase.get_state(source, sub_source)
            if state and state.get("last_timestamp"):
                self.local_state[key] = state
                self._save_local()
                return state["last_timestamp"]
        except Exception as e:
            print(f"  [StateManager] Supabase read failed for {key}, using local: {e}")

        # Fallback to local
        if key in self.local_state:
            return self.local_state[key].get("last_timestamp")

        return None

    def set_watermark(self, source: str, sub_source: str, timestamp: str, record_id: str, new_records: int = 0):
        """Update watermark after successful collection."""
        key = f"{source}:{sub_source}"

        # Update local
        self.local_state[key] = {
            "last_timestamp": timestamp,
            "last_record_id": record_id,
            "record_count": self.local_state.get(key, {}).get("record_count", 0) + new_records
        }
        self._save_local()

        # Update Supabase
        try:
            self.supabase.set_state(source, sub_source, timestamp, record_id, new_records)
        except Exception as e:
            print(f"  [StateManager] Supabase write failed for {key}: {e}")

    def get_all_watermarks(self) -> Dict[str, Dict[str, Any]]:
        """Get all watermarks as dict."""
        return self.local_state

    def reset(self, source: str = None, sub_source: str = None):
        """Reset watermarks. If source/sub_source specified, reset only that."""
        if source and sub_source:
            key = f"{source}:{sub_source}"
            self.local_state.pop(key, None)
            try:
                # Can't easily delete from Supabase without direct SQL
                pass
            except:
                pass
        else:
            self.local_state = {}
        self._save_local()
