# LeetCode Trainer

Personal LeetCode review trainer: structured notes + Ebbinghaus-style spaced repetition + AI-generated quiz cards + weekly progress reports.

- **Backend**: FastAPI + SQLite (stdlib `sqlite3`) + httpx
- **Frontend**: plain HTML + Tailwind CDN + vanilla JS (no build step)
- **AI**: unified abstraction layer, switch between Gemini / Vertex / DeepSeek / Claude with a single env var
- **Bilingual UI**: defaults to English, one-click toggle to Chinese (preference persists per browser)
- **Target deployment**: 1 GB RAM Ubuntu VM (e.g. Oracle Cloud always-free) behind Caddy

## Features

- **Today's review** (home page): groups every problem with cards due today; one click to drill in
- **Add / edit problem**: enter just the LC problem #, the rest (title, difficulty, tags) auto-fills from leetcode.com. Notes are split into four structured fields:
  - ① Approach clarity (yes/no — "no" forces an extra "describe the approach" question in quizzes)
  - ② Syntax errors / language pitfalls
  - ③ Style / optimization (not wrong, but could be better)
  - ④ Other notes (Markdown, optional)
- **AI-generated quiz cards**: the "Generate cards" button feeds your structured notes into the LLM, which returns 3-5 testable questions (with hints and reference answers). Each card is persisted with its own Ebbinghaus state.
- **Spaced repetition per card**: cards are the unit of review, not the problem. Marks (`Got it / Fuzzy / Forgot`) advance, hold, or reset each card's schedule independently.
- **Calendar view**: month grid showing how many cards are scheduled each day.
- **Weekly report**: AI summarizes new problems, review activity, and recurring weak points.
- **Per-card edit / delete**: AI sometimes generates fluff. Edit or delete cards inline.

## Project structure

```
leetcode-trainer/
├── main.py              # FastAPI entry: routing, middleware, lifespan
├── database.py          # SQLite schema + CRUD + automatic migrations
├── scheduler.py         # Ebbinghaus interval logic
├── ai_service.py        # Unified async LLM client (4 providers)
├── leetcode_lookup.py   # Public LeetCode API helper (cached)
├── config.py            # Env-driven configuration
├── models.py            # Pydantic v2 request models
├── requirements.txt
├── static/js/
│   ├── app.js           # Shared frontend utilities
│   └── i18n.js          # Client-side translation dictionary
├── templates/           # 8 Jinja2 pages
│   ├── base.html  login.html  index.html  add.html
│   ├── list.html  review.html  calendar.html  settings.html
├── data/                # SQLite database (auto-created, gitignored)
├── deploy/
│   ├── leetcode-trainer.service   # systemd unit
│   └── Caddyfile                  # reverse proxy template
├── .env.example
└── README.md
```

## Local setup

```bash
git clone <repo> leetcode-trainer
cd leetcode-trainer

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env, fill in GOOGLE_API_KEY (or DeepSeek / Claude). AUTH_TOKEN can be empty for local dev.

python main.py
# Or: uvicorn main:app --host 127.0.0.1 --port 8765 --reload
```

Open <http://127.0.0.1:8765/>. The SQLite database is created automatically at `data/tracker.db`.

## AI providers

The app talks to each provider's REST API directly via `httpx` — no `google-genai` / `openai` / `anthropic` SDK is bundled, keeping the install small. Pick one in `.env`:

| Provider  | `AI_PROVIDER` | Default model      | Auth                                      |
|-----------|---------------|--------------------|-------------------------------------------|
| Gemini    | `gemini`      | `gemini-2.0-flash` | `GOOGLE_API_KEY`                          |
| Vertex AI | `vertex`      | `gemini-2.5-flash` | GCP Application Default Credentials       |
| DeepSeek  | `deepseek`    | `deepseek-chat`    | `DEEPSEEK_API_KEY`                        |
| Claude    | `claude`      | `claude-sonnet-4-5`| `ANTHROPIC_API_KEY`                       |

Restart the server after switching.

### Using Vertex AI to burn the GCP $300 credit

Vertex doesn't accept static API keys — auth goes through OAuth2. One-time setup:

```bash
# 1) Create or pick a GCP project (link a billing account so the $300 credit applies)
# 2) Enable Vertex AI API
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID

# 3) Service account with the minimum role
gcloud iam service-accounts create leetcode-trainer \
    --display-name="LeetCode Trainer Vertex caller" \
    --project=YOUR_PROJECT_ID

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:leetcode-trainer@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

# 4) Download a JSON key
gcloud iam service-accounts keys create ~/leetcode-trainer-vertex.json \
    --iam-account=leetcode-trainer@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

Copy the JSON to your server (e.g. `/opt/leetcode-trainer/vertex-key.json`, `chmod 600`), then in `.env`:

```ini
AI_PROVIDER=vertex
VERTEX_PROJECT=YOUR_PROJECT_ID
VERTEX_LOCATION=us-central1
VERTEX_MODEL=gemini-2.5-flash
GOOGLE_APPLICATION_CREDENTIALS=/opt/leetcode-trainer/vertex-key.json
```

`google-auth` is the only extra dependency (already in `requirements.txt`; comment it out if you never use Vertex).

**Local dev shortcut**: instead of downloading a JSON key, run `gcloud auth application-default login`. `google-auth` will then find your credentials at `~/.config/gcloud/application_default_credentials.json` automatically; leave `GOOGLE_APPLICATION_CREDENTIALS` blank.

## Deployment (Oracle Cloud, 1 GB Ubuntu)

```bash
# 1) Code on the box
sudo mkdir -p /opt/leetcode-trainer
sudo chown $USER /opt/leetcode-trainer
git clone <repo> /opt/leetcode-trainer
cd /opt/leetcode-trainer

# 2) Dependencies
sudo apt update && sudo apt install -y python3-venv caddy
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3) Configuration
cp .env.example .env
# Required edits:
#   AI_PROVIDER=vertex
#   GOOGLE_APPLICATION_CREDENTIALS=/opt/leetcode-trainer/vertex-key.json
#   AUTH_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
nano .env

# 4) systemd
sudo cp deploy/leetcode-trainer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now leetcode-trainer
sudo systemctl status leetcode-trainer

# 5) Caddy reverse proxy (point your DNS A record at this VM first)
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile     # replace your.domain.com
sudo systemctl reload caddy
```

Visit <https://your.domain.com>, enter the `AUTH_TOKEN` you generated, and you're in.

**Oracle Cloud firewall reminder**: there are TWO layers — VCN security list (Console) AND host iptables (`sudo iptables -L`). Both must allow 80/443 inbound. Many first-time deployments stall here.

## API quick reference

Every `/api/*` endpoint accepts both an `auth_token` cookie and an `X-Auth-Token` header.

```bash
curl https://your.domain.com/api/today \
     -H "X-Auth-Token: $AUTH_TOKEN"
```

Highlights:

- `GET  /api/today` — problems with cards due today (or no cards yet)
- `POST /api/problems` — create a problem (`lc_number`, `title`, `difficulty`, `tags`, `approach_clear`, `approach_desc`, `syntax_errors`, `style_issues`, `notes`)
- `GET  /api/problems?sort=&order=&difficulty=&tag=`
- `GET  /api/problems/by-lc/{lc_number}` — look up by LeetCode question number
- `GET  /api/leetcode-meta/{lc_number}` — fetch canonical title/difficulty/tags from leetcode.com
- `GET  /api/problems/{id}/cards` — list cards
- `POST /api/problems/{id}/cards/generate` — append AI-generated cards
- `PUT  /api/cards/{id}` / `DELETE /api/cards/{id}` — edit / delete card
- `POST /api/cards/{id}/mark` — body `{"status":"remembered|fuzzy|forgot"}`
- `GET  /api/calendar?year=&month=`
- `GET  /api/weekly-report`
- `GET/PUT /api/settings/intervals`

## Scheduling algorithm

Default interval list: `[1, 2, 4, 7, 15, 30, 60]` days (editable on the Settings page). Each card has:

- `review_step` — index into the interval list
- `ease_factor` — multiplier on the base interval, starts at 2.5, clamped to [1.3, 3.0]

| Mark        | Step change | Ease change |
|-------------|-------------|-------------|
| Remembered  | +1          | +0.05       |
| Fuzzy       | unchanged   | unchanged   |
| Forgot      | reset to 0  | -0.2        |

Actual delay = `intervals[new_step] * (ease_factor / 2.5)` days. So a card you keep getting wrong has its ease pulled down, accelerating the next visit.

## FAQ

- **Database error on first run** — make sure `data/` is writable; if running under systemd, the `User=` directive must match the directory owner.
- **AI returns 401** — check the API key has no leading/trailing spaces, and that `AI_PROVIDER` matches the key you set.
- **Where do I change the review intervals?** — `/settings`, top section.
- **Memory** — the systemd unit caps the process at 400 MB. The actual footprint is usually under 100 MB.

## License

Personal project, take what you want.
