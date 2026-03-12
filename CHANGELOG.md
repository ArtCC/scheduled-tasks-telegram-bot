# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.0.4] — 2026-03-12

### Added
- Free text messages (without `/` prefix) now query the LLM instantly, just like `/ask`.
- Updated `/start` help text to reflect free text query capability.

### Changed
- Removed decorative separator lines (━━━━━━━━━━━━━━━━━━) from all bot messages for a cleaner, more consistent UI.

---

## [0.0.3] — 2026-03-10

### Added
- Persistent `ReplyKeyboardMarkup` with four buttons: **📋 My Tasks**, **➕ New Task**, **📊 Status**, **❓ Help**.
- Keyboard is shown on `/start`, `/help`, and after every successful task creation.
- `➕ New Task` button displays a contextual guide listing `/add`, `/every`, and `/remember`.
- `CONTRIBUTING.md` with setup, workflow, code style, UX/UI rules, and PR guidelines.

### Changed
- `/delete <id>` now shows an inline Confirm / Cancel prompt instead of deleting immediately, matching the behaviour of the inline 🗑️ button in `/list`.
- All "not found" and "invalid ID" error messages updated to follow the **❌ what failed → cause → 💡 next step** pattern from the UX guidelines.
- Usage hints for `/run`, `/edit`, `/clone`, `/pause`, `/resume`, and `/delete` now include `ℹ️` icon and a concrete example.
- After a confirmed inline deletion, the bot sends a `✅ Task deleted.` confirmation with the persistent keyboard visible.
- Callback "Task not found" responses now use `❌` prefix for consistency.

---

## [0.0.2] — 2025

### Added
- `/clone <id>` command to duplicate an existing task.
- Inline 🗑️ Delete button now shows a Confirm / Cancel prompt before removing a task.
- `/remember` command for plain-text reminders without AI processing.
- Task names via `--name=X` flag in `/add`.
- Day-of-week filtering in `/add` and `/remember` (e.g. `mon,wed,fri`).
- `/every <interval> <prompt>` for interval-based tasks (e.g. `2h`, `30m`).
- `/run <id>` to execute any task on demand.
- `/edit <id> <new prompt>` to modify an existing task prompt.
- Inline buttons (▶️ Run, ⏸️ Pause / ▶️ Resume, 🗑️ Delete) rendered per task in `/list`.
- Timezone support per task (IANA format, e.g. `Europe/Madrid`).
- One-time ISO datetime tasks (`/add 2026-12-31T23:00 message`).
- Web search capability via OpenAI Responses API.
- Configurable model via `OPENAI_MODEL` env variable.
- `/status` command showing scheduler state, active/paused task counts, and next run time.
- Typing indicator (`send_chat_action`) on long operations.
- `ALLOWED_CHAT_IDS` authorization middleware.
- Comprehensive test suite (`test_formatting`, `test_models`, `test_scheduler`, `test_storage`).
- Docker image published to GHCR on every release.

### Changed
- Migrated OpenAI client to the Responses API.
- All user-facing messages and command descriptions translated to English.
- Increased default token and character limits (`OPENAI_MAX_TOKENS`, `MAX_RESPONSE_CHARS`).
- Improved HTML fallback handling when Telegram rejects formatted messages.

---

## [0.0.1] — 2025

### Added
- Initial implementation: `/start`, `/help`, `/ask`, `/add` (daily HH:MM), `/list`, `/pause`, `/resume`, `/delete`.
- APScheduler-based scheduling with SQLite persistence.
- OpenAI integration for AI-generated responses.
- Docker / Docker Compose setup with CI and publish workflows.
- `ALLOWED_CHAT_IDS` environment variable.
- `setMyCommands` registration for the Telegram bot menu.

---

[0.0.3]: https://github.com/ArtCC/scheduled-tasks-telegram-bot/compare/0.0.2...0.0.3
[0.0.2]: https://github.com/ArtCC/scheduled-tasks-telegram-bot/compare/0.0.1...0.0.2
[0.0.1]: https://github.com/ArtCC/scheduled-tasks-telegram-bot/releases/tag/0.0.1
