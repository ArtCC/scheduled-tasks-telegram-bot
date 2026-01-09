# 🤖 Scheduled Tasks Telegram Bot

[![CI](https://github.com/artcc/scheduled-tasks-telegram-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/artcc/scheduled-tasks-telegram-bot/actions/workflows/ci.yml)
[![Docker](https://github.com/artcc/scheduled-tasks-telegram-bot/actions/workflows/publish.yml/badge.svg)](https://github.com/artcc/scheduled-tasks-telegram-bot/actions/workflows/publish.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

> Telegram bot to schedule AI-generated messages using the OpenAI Responses API with web search. Responses are delivered in Telegram HTML format with APScheduler-based scheduling and SQLite persistence.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 💬 **Instant queries** | `/ask question` — get answers immediately |
| 🕐 **Daily schedules** | `/add 08:00 your request` — runs every day at that time |
| 📆 **Specific days** | `/add 08:00 mon,wed,fri ...` — runs only on selected days |
| ⏱️ **Interval tasks** | `/every 2h your request` — runs at fixed intervals |
| 📅 **One-time tasks** | `/add 2026-12-31T23:00 message` — runs once at ISO datetime |
| 🏷️ **Task names** | `/add 08:00 --name=News ...` — give tasks friendly names |
| 🌍 **Timezone support** | `/add 08:00 Europe/Madrid ...` — per-task timezone |
| ⏸️ **Pause/Resume** | Pause tasks without deleting them |
| ▶️ **Run on demand** | `/run <id>` — execute any task immediately |
| ✏️ **Edit tasks** | `/edit <id> <new prompt>` — modify existing tasks |
| 🔘 **Inline buttons** | Manage tasks with interactive buttons |
| 🔒 **Private by default** | Only authorized chat IDs can use the bot |
| 💾 **Persistent storage** | SQLite database survives container restarts |
| 🐳 **Docker ready** | Pre-built image on GHCR, Portainer-friendly |
| 🔍 **Web search** | AI can search the internet for up-to-date information |
| 🤖 **Flexible models** | Use any OpenAI model (gpt-5, gpt-4o, gpt-4.1-mini, etc.) |

---

## 🚀 Quick Start

### 1. Get your credentials

- **Telegram Bot Token**: Create a bot with [@BotFather](https://t.me/BotFather)
- **OpenAI API Key**: Get one from [platform.openai.com](https://platform.openai.com/api-keys)
- **Your Chat ID**: Send any message to [@userinfobot](https://t.me/userinfobot)

### 2. Deploy with Docker

```bash
docker pull ghcr.io/artcc/scheduled-tasks-telegram-bot:latest
```

Create a `docker-compose.yml` or use [the one in this repo](docker-compose.yml), then configure your environment variables in Portainer or a `.env` file.

---

## ⚙️ Environment Variables

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `BOT_TOKEN` | ✅ | — | Telegram bot token from BotFather |
| `OPENAI_API_KEY` | ✅ | — | OpenAI API key |
| `ALLOWED_CHAT_IDS` | ✅ | — | Comma-separated list of authorized chat IDs |
| `OPENAI_MODEL` | ❌ | `gpt-4.1-mini` | OpenAI model to use |
| `TIMEZONE` | ❌ | `UTC` | Default timezone (IANA format) |
| `DATABASE_PATH` | ❌ | `/app/data/bot.db` | SQLite database path |
| `OPENAI_MAX_TOKENS` | ❌ | `4096` | Max tokens per response |
| `OPENAI_TEMPERATURE` | ❌ | `0.4` | Model temperature |
| `MAX_PROMPT_CHARS` | ❌ | `4000` | Max prompt length |
| `MAX_RESPONSE_CHARS` | ❌ | `4000` | Max response length |
| `OPENAI_MAX_RETRIES` | ❌ | `3` | Retries with exponential backoff |

> 💡 See [.env.example](.env.example) for a complete template.

---

## 📱 Bot Commands

### Task Creation

| Command | Description |
|---------|-------------|
| `/ask <question>` | Ask a question and get an instant response |
| `/add HH:MM [TZ] [days] [--name=X] <prompt>` | Create a scheduled task |
| `/add YYYY-MM-DDTHH:MM [--name=X] <prompt>` | Create a one-time task (ISO 8601) |
| `/every <interval> <prompt>` | Create an interval task (e.g., `2h`, `30m`, `1h30m`) |

### Task Management

| Command | Description |
|---------|-------------|
| `/list` | List all tasks with interactive buttons |
| `/run <id>` | Execute a task immediately |
| `/edit <id> <new prompt>` | Edit an existing task's prompt |
| `/pause <id>` | Pause a task (won't run until resumed) |
| `/resume <id>` | Resume a paused task |
| `/delete <id>` | Delete a task permanently |
| `/status` | Show bot status and next scheduled run |
| `/start`, `/help` | Show help message |

### Examples

```text
/ask What's the latest news about AI?
/add 08:00 Give me a daily weather summary for Madrid
/add 09:15 Europe/London Summarize key crypto news
/add 09:00 mon,wed,fri Weekly standup summary
/add 08:00 --name=News Daily tech headlines
/add 08:00 Europe/Madrid mon,fri --name=Report Weekly report
/add 2026-01-15T07:30 Create a checklist for today's meeting
/every 2h Check server status and report issues
/every 30m Get latest Bitcoin price
/run 1
/edit 1 New prompt for the task
/pause 2
/status
```

### Interval Formats

| Format | Example | Description |
|--------|---------|-------------|
| `Xh` | `2h` | Every X hours |
| `Xm` | `30m` | Every X minutes |
| `XhYm` | `1h30m` | Every X hours and Y minutes |

### Day Abbreviations

| Days | |
|------|-----|
| `mon` | Monday |
| `tue` | Tuesday |
| `wed` | Wednesday |
| `thu` | Thursday |
| `fri` | Friday |
| `sat` | Saturday |
| `sun` | Sunday |

Combine with commas: `mon,wed,fri`, `sat,sun`

> ⚠️ Timezones must be valid IANA names: `UTC`, `Europe/Madrid`, `America/New_York`, etc.
> 
> 💡 Maximum interval is 24 hours. Minimum is 1 minute.

---

## 🐳 Docker Deployment

### Option A: Portainer (recommended)

1. Go to **Stacks → Add stack**
2. Paste the [docker-compose.yml](docker-compose.yml) content or import from Git
3. Add environment variables:
   - `BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `ALLOWED_CHAT_IDS`
4. Deploy

### Option B: Docker Compose with `.env`

```bash
# Copy and edit environment file
cp .env.example .env

# Create override file
cat > docker-compose.override.yml << 'OVERRIDE'
services:
  bot:
    env_file:
      - .env
OVERRIDE

# Start the bot
docker compose up -d
```

### Useful commands

```bash
# View logs
docker compose logs -f

# Update to latest image
docker compose pull && docker compose up -d

# Build locally (development)
docker compose build && docker compose up -d
```

---

## 🛠️ Local Development

```bash
# Install dependencies
make install

# Run the bot
make run

# Lint and test
make lint
make test
```

---

## 📁 Project Structure

```text
src/scheduled_bot/
├── __main__.py      # Entry point, bot bootstrap
├── telegram_bot.py  # Command handlers & auth middleware
├── scheduler.py     # APScheduler task management
├── openai_client.py # OpenAI Responses API with web search
├── formatting.py    # HTML escaping for Telegram
├── storage.py       # SQLite persistence
├── config.py        # Settings from environment
└── models.py        # Data models
```

---

## 🔄 CI/CD

| Workflow | Trigger | Action |
|----------|---------|--------|
| [ci.yml](.github/workflows/ci.yml) | Push/PR | Lint (ruff), format (black), tests |
| [publish.yml](.github/workflows/publish.yml) | Push to `main` or tags | Build & push to GHCR |

Docker images:
- `ghcr.io/artcc/scheduled-tasks-telegram-bot:latest` — latest from main
- `ghcr.io/artcc/scheduled-tasks-telegram-bot:v1.0.0` — tagged releases

---

## 📄 License

[Apache-2.0](LICENSE)

---

<p align="left">
  <sub>100% built with GitHub Copilot (Claude Opus 4.5)</sub><br>
  <sub>Arturo Carretero Calvo — 2026</sub>
</p>