# Scheduled Tasks Telegram Bot

Telegram bot to schedule messages generated with the OpenAI API, always delivered in Telegram MarkdownV2. Includes APScheduler-based scheduling, SQLite persistence, and Docker deployment.

## How it works
- Sends responses directly to your Telegram chat in MarkdownV2.
- Daily schedules with fixed time (`/add 08:00 whatever you want`).
- One-off runs with ISO datetime (`/add 2025-12-31T23:00 one-time message`).
- Basic commands: `/add`, `/list`, `/delete <id>`, `/start` (help).
- Tasks are persisted in SQLite to survive restarts.

## Requirements
- Python 3.11+
- Telegram BotFather token (`BOT_TOKEN`).
- OpenAI API key (`OPENAI_API_KEY`).

## Environment variables
Create a `.env` from [.env.example](.env.example):
- `BOT_TOKEN`: Telegram bot token.
- `OPENAI_API_KEY`: OpenAI key.
- `OPENAI_MODEL`: model to use (default `gpt-4.1-mini`).
- `TIMEZONE`: scheduler timezone, e.g. `Europe/Madrid`.
- `DATABASE_PATH`: SQLite path, default `./data/bot.db`.
- `OPENAI_MAX_TOKENS`: max tokens per response (default 400).
- `OPENAI_TEMPERATURE`: model temperature (default 0.4).
- `MAX_PROMPT_CHARS`: max prompt length (default 1200).
- `MAX_RESPONSE_CHARS`: max response length before sending to Telegram (default 3500).
- `OPENAI_MAX_RETRIES`: retries with backoff for OpenAI calls (default 3).

## Local development
1) Create venv and deps:
```
make install
```
2) Run the bot (long polling):
```
make run
```
3) Lint and tests:
```
make lint
make test
```

Entry point: [src/scheduled_bot/__main__.py](src/scheduled_bot/__main__.py).

## Bot usage (commands)
- `/start` or `/help`: quick help.
- `/add HH:MM [Timezone] message`: daily schedule. Example: `/add 08:00 Europe/Madrid ...`.
- `/add YYYY-MM-DDTHH:MM message`: one-time run (ISO 8601, uses configured TZ or the one provided in the command).
- `/list`: list tasks with IDs.
- `/delete <id>`: delete a task you own.

Notes:
- Timezones must be valid IANA names (e.g., `UTC`, `Europe/Madrid`, `America/New_York`). Invalid values return a clear error.

### Prompt examples
- `/add 08:00 Give me a daily weather summary for Madrid in 3 bullets.`
- `/add 09:15 Summarize key crypto news in 5 bullets.`
- `/add 2025-01-10T07:30 Create a checklist for today’s meeting.`

### Length and format
- The bot enforces Telegram MarkdownV2 and escapes special characters automatically.
- Prompt and response lengths are capped; long responses are truncated with the suffix `…[truncado]`.

## Docker deployment
1) Copy `.env.example` to `.env` and fill values.
2) Build and start with compose:
```
docker compose up --build -d
```
3) Logs:
```
docker compose logs -f
```

Base image: [Dockerfile](Dockerfile). Compose service: [docker-compose.yml](docker-compose.yml).

### Using the published GHCR image
- Expected image: `ghcr.io/<your-user>/scheduled-tasks-telegram-bot:latest` (or the tag you publish).
- Pull directly:
```
docker pull ghcr.io/<your-user>/scheduled-tasks-telegram-bot:latest
```
- In `docker-compose.yml`, replace the build section with:
```
  image: ghcr.io/<your-user>/scheduled-tasks-telegram-bot:latest
```
- If the repo is public, no login is needed. If private, log in first:
```
echo $GITHUB_TOKEN | docker login ghcr.io -u <your-user> --password-stdin
```

## Project structure
- [src/scheduled_bot/__main__.py](src/scheduled_bot/__main__.py): bot and scheduler bootstrap.
- [src/scheduled_bot/telegram_bot.py](src/scheduled_bot/telegram_bot.py): commands and handlers.
- [src/scheduled_bot/scheduler.py](src/scheduled_bot/scheduler.py): task scheduling and execution.
- [src/scheduled_bot/openai_client.py](src/scheduled_bot/openai_client.py): OpenAI call with MarkdownV2 instructions.
- [src/scheduled_bot/formatting.py](src/scheduled_bot/formatting.py): safe MarkdownV2 escaping.
- [src/scheduled_bot/storage.py](src/scheduled_bot/storage.py): SQLite persistence for tasks.
- [tests](tests): basic tests.

## CI
GitHub Actions workflow [.github/workflows/ci.yml](.github/workflows/ci.yml) runs lint (ruff), format (black), and tests. Workflow [.github/workflows/publish.yml](.github/workflows/publish.yml) builds and pushes the Docker image to GHCR on main/master and tags.

## License
Apache-2.0 (see [LICENSE](LICENSE)).

---

<sub>Arturo Carretero Calvo - 2026</sub>
<sub>100% built with GitHub Copilot (model GPT-5.1-Codex-Max)</sub>