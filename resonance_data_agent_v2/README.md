# Resonance Data Agent v2

**Incremental. Live 24/7. Supabase-backed.**

This agent automatically collects social media data from multiple free sources, stores it in Supabase (PostgreSQL), and keeps running forever — pulling only **new** data on each cycle.

---

## What It Does

| Mode | What Happens | Use When |
|------|-------------|----------|
| `--init` | Big pull: ignores watermarks, collects everything | First time setup |
| `--live` | Runs forever: checks every 15-30 mins for new data | Production / 24/7 |
| `--incremental` | One run: pulls only new data since last time | Testing / manual trigger |
| `--status` | Shows total record count in Supabase | Checking health |
| `--reset` | Clears all watermarks | Starting over |

**Sources:**
- **Reddit** (FREE) - 10 subreddits, checks every 15 minutes
- **YouTube** (FREE with API key) - channels, checks every 30 minutes
- **Kaggle** (FREE) - datasets, checks every 24 hours for updates
- **Hugging Face** (FREE) - datasets, checks every 24 hours for updates
- **Web Scraper** (FREE, optional) - public pages, checks every 6 hours

**Storage:** All data goes to **Supabase** (PostgreSQL) with a unified schema. Optional local Parquet/CSV backup.

---

## Quick Start

### Step 1: Create a Supabase Project (5 minutes)

1. Go to [supabase.com](https://supabase.com) and sign up
2. Create a new project (free tier is fine)
3. Wait for the project to be ready
4. Go to **Project Settings > API**
5. Copy:
   - **Project URL** (e.g., `https://xyzabc123.supabase.co`)
   - **Service Role Key** (starts with `eyJ...` — keep this secret!)
6. Go to **Project Settings > Database**
7. Copy:
   - **Database Password** (you set this when creating the project)
   - **Connection String** (host is like `db.xyzabc123.supabase.co`)

### Step 2: Run the SQL Setup

1. In Supabase Dashboard, go to **SQL Editor**
2. Click **New Query**
3. Copy everything from `sql/setup.sql` in this folder
4. Paste and click **Run**
5. You should see "raw_data table created" and "collection_state table created"

### Step 3: Configure the Agent

Edit `config.yaml`:

```yaml
supabase:
  project_url: "https://YOUR_PROJECT.supabase.co"
  service_role_key: "eyJ...YOUR_KEY..."
  db_password: "YOUR_DB_PASSWORD"
  db_host: "db.YOUR_PROJECT.supabase.co"
  db_port: 5432
  db_name: "postgres"
  db_user: "postgres"
  use_direct_postgres: true

youtube_api_key: "YOUR_YOUTUBE_API_KEY"
```

**Get YouTube API key:**
1. [Google Cloud Console](https://console.cloud.google.com/)
2. Create project → Enable "YouTube Data API v3"
3. Create credentials → API Key
4. Paste in config.yaml

### Step 4: Install & Run

```bash
pip install -r requirements.txt

# First: do the big initial pull
python main.py --init

# Then: start 24/7 live collection
python main.py --live
```

The `--init` run will collect 20,000–50,000 baseline records. The `--live` run will keep checking for new data every 15-30 minutes, forever.

**Press Ctrl+C to stop.**

---

## How Incremental Works

The agent stores a **watermark** (timestamp/hash) for every source in Supabase:

| Source | Watermark | Meaning |
|--------|-----------|---------|
| Reddit | `last_post_timestamp` | Only fetch posts AFTER this time |
| YouTube | `last_video_published` | Only fetch videos AFTER this date |
| Kaggle | `file_hash` | Only re-process if file changed |
| HuggingFace | `dataset_version` | Only re-load if version changed |

Watermarks are stored in:
- **Supabase** `collection_state` table (primary)
- **Local** `.state.json` file (backup if Supabase is down)

On each run, the agent reads the watermark, fetches only newer data, inserts it, and updates the watermark.

---

## Database Schema

### `raw_data` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Auto-generated primary key |
| `record_id` | TEXT | Unique ID from source (prevents duplicates) |
| `source` | TEXT | `reddit`, `youtube`, `kaggle`, `huggingface`, `scraper` |
| `content_type` | TEXT | `post`, `comment`, `video`, `profile`, `review`, `campaign` |
| `author_id` | TEXT | Creator/user ID |
| `author_name` | TEXT | Creator/user name |
| `text` | TEXT | Main content text |
| `title` | TEXT | Title/headline |
| `platform` | TEXT | `reddit`, `youtube`, `instagram`, `tiktok`, `amazon` |
| `channel` | TEXT | Subreddit, channel name, category |
| `likes` | BIGINT | Upvotes, likes |
| `comments` | BIGINT | Comment count |
| `views` | BIGINT | View count |
| `created_at` | TIMESTAMPTZ | When the content was originally posted |
| `collected_at` | TIMESTAMPTZ | When we collected it |
| `metadata` | JSONB | Source-specific extra fields |
| `subculture_tags` | JSONB | **Empty** — fill with your intelligence layer |
| `value_keywords` | JSONB | **Empty** — fill with your intelligence layer |
| `sentiment` | TEXT | **Empty** — fill with your intelligence layer |
| `resonance_score` | FLOAT | **Empty** — fill with your intelligence layer |

### `collection_state` table

| Column | Type | Description |
|--------|------|-------------|
| `source` | TEXT | Collector name |
| `sub_source` | TEXT | e.g., subreddit name, channel ID |
| `last_timestamp` | TEXT | Watermark value |
| `last_record_id` | TEXT | Last record seen |
| `record_count` | BIGINT | Cumulative records from this source |
| `updated_at` | TIMESTAMPTZ | Last update time |

---

## Commands Reference

```bash
# First-time setup: big pull
python main.py --init

# Start 24/7 daemon
python main.py --live

# One incremental run (all sources)
python main.py --incremental

# Check database status
python main.py --status

# Reset and start over
python main.py --reset
python main.py --init

# Use custom config
python main.py --init --config my_config.yaml
```

---

## Scheduler Intervals (configurable in config.yaml)

| Collector | Default Interval | Why |
|-----------|-----------------|-----|
| Reddit | 15 minutes | Subreddits are active, fast-moving |
| YouTube | 30 minutes | Videos publish less frequently |
| Kaggle | 24 hours | Datasets update rarely |
| HuggingFace | 24 hours | Datasets update rarely |
| Scraper | 6 hours | Public pages change slowly |

Edit `config.yaml` under `scheduler:` to change these.

---

## Cost

| Item | Cost | Notes |
|------|------|-------|
| Supabase Free Tier | ₹0 | 500MB storage, 2GB bandwidth, enough for 100k+ records |
| YouTube API | ₹0 | 10,000 quota units/day |
| Reddit (Arctic Shift) | ₹0 | No limits, be polite |
| Kaggle | ₹0 | Public datasets |
| Hugging Face | ₹0 | Public datasets |
| VPS to run agent | ₹500–1,500/month | Cheapest DigitalOcean/Linode/EC2 |
| **Total** | **Under ₹2,000/month** | |

---

## Troubleshooting

**"Supabase connection failed"**
→ Check `project_url` and `service_role_key` in config.yaml. Make sure there's no trailing slash on the URL.

**"Tables may not exist"**
→ Run `sql/setup.sql` in Supabase SQL Editor first.

**"YouTube health check failed"**
→ Add your API key to config.yaml or set `YOUTUBE_API_KEY` environment variable.

**"No new records on incremental"**
→ Watermarks are working correctly — there just isn't new data yet. Wait 15-30 minutes.

**"kagglehub not installed"**
→ Run `pip install kagglehub`

**"datasets library not installed"**
→ Run `pip install datasets`

---

## Architecture

```
                    ┌─────────────┐
     YouTube API    │   Reddit    │
          ↓         │  (Arctic)   │
    ┌─────────┐     └──────┬──────┘
    │ YouTube │            │
    │Collector│            │
    └────┬────┘            │
         │                 │
    ┌────┴────┐      ┌────┴────┐
    │         │      │         │
┌───▼───┐ ┌──▼────┐ ┌▼──────┐ ┌──────────┐
│Kaggle │ │Hugging│ │Scraper│ │  State   │
│Collect│ │Face   │ │Collect│ │ Manager  │
└───┬───┘ └──┬────┘ └──┬────┘ └────┬─────┘
    │        │         │           │
    └────────┴─────────┴───────────┘
                  │
            ┌─────▼─────┐
            │  Compiler   │
            │  (batcher)  │
            └─────┬─────┘
                  │
        ┌─────────┴──────────┐
        │                    │
   ┌────▼────┐         ┌─────▼─────┐
   │Supabase │         │Local Backup│
   │(Primary)│         │ (Parquet)  │
   └─────────┘         └────────────┘
```

---

## Next Step

Once data is flowing, your intelligence layer reads from Supabase:

```python
from supabase import create_client

sb = create_client("YOUR_URL", "YOUR_KEY")
resp = sb.table("raw_data").select("*").eq("source", "reddit").limit(1000).execute()

for record in resp.data:
    text = record["text"]
    # Run subculture detection, value extraction, resonance scoring...
```

The data agent and intelligence layer are completely separate. The agent just keeps your database full of fresh raw material.
