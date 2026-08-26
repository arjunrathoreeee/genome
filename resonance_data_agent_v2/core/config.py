"""Load config from YAML."""
import yaml
import os


class Config:
    def __init__(self, path="config.yaml"):
        with open(path, "r") as f:
            self.data = yaml.safe_load(f)

    def get(self, key, default=None):
        keys = key.split(".")
        val = self.data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    def is_enabled(self, name):
        return self.get(f"collectors.{name}", False)

    def get_api_key(self, service):
        env = os.environ.get(f"{service.upper()}_API_KEY", "")
        return env or self.get(f"{service}_api_key", "")

    def get_supabase_creds(self):
        """Return Supabase credentials dict."""
        return {
            "project_url": self.get("supabase.project_url", ""),
            "service_role_key": self.get("supabase.service_role_key", ""),
            "db_password": self.get("supabase.db_password", ""),
            "db_host": self.get("supabase.db_host", ""),
            "db_port": self.get("supabase.db_port", 5432),
            "db_name": self.get("supabase.db_name", "postgres"),
            "db_user": self.get("supabase.db_user", "postgres"),
            "use_direct_postgres": self.get("supabase.use_direct_postgres", True),
        }
