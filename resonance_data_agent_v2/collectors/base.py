"""Base class for all collectors with incremental support."""
from abc import ABC, abstractmethod


class BaseCollector(ABC):
    name = "base"

    def __init__(self, config, state_manager=None):
        self.config = config
        self.state = state_manager
        self.stats = {"records": 0, "new_records": 0, "errors": 0, "batches": 0}

    @abstractmethod
    def collect(self, init_mode=False):
        """Yield batches of UnifiedRecord.

        init_mode=True: Pull everything, ignore watermarks.
        init_mode=False: Pull only new data since last watermark.
        """
        pass

    def health_check(self):
        return True

    def get_stats(self):
        return self.stats

    def _get_watermark(self, sub_source):
        """Get watermark for this source+sub_source."""
        if self.state:
            return self.state.get_watermark(self.name, sub_source)
        return None

    def _set_watermark(self, sub_source, timestamp, record_id, count=0):
        """Update watermark after collection."""
        if self.state:
            self.state.set_watermark(self.name, sub_source, timestamp, record_id, count)
