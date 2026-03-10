# Contributing

Thank you for taking the time to contribute!
Please read this guide before opening an issue or submitting a pull request.

## Table of contents

- [Code of conduct](#code-of-conduct)
- [Getting started](#getting-started)
- [Development workflow](#development-workflow)
- [Code style](#code-style)
- [Tests](#tests)
- [Submitting a pull request](#submitting-a-pull-request)
- [Reporting bugs](#reporting-bugs)
- [Requesting features](#requesting-features)

---

## Code of conduct

Be respectful and constructive in all interactions.
Harassment or discriminatory language of any kind will not be tolerated.

---

## Getting started

### Prerequisites

- Python 3.11+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An OpenAI API key

### Set up the environment

```bash
git clone https://github.com/your-org/scheduled-tasks-telegram-bot.git
cd scheduled-tasks-telegram-bot
make install
```

Create a `.env` file based on the project README and fill in your credentials
before running or testing.

---

## Development workflow

1. Fork the repository and create your branch from `main`:

   ```bash
   git checkout -b feat/your-feature-name
   ```

2. Make your changes.

3. Lint and format:

   ```bash
   make lint
   make fmt
   ```

4. Run the test suite:

   ```bash
   make test
   ```

5. Commit using the [Conventional Commits](https://www.conventionalcommits.org) format:

   ```
   feat: add /snooze command
   fix: handle missing timezone in /add
   docs: update README examples
   refactor: extract _build_confirmation_keyboard helper
   test: add coverage for parse_interval edge cases
   ```

6. Push your branch and open a pull request against `main`.

---

## Code style

This project uses **Ruff** for linting and **Black** for formatting.
Both are configured in `ruff.toml` and `pyproject.toml`.

- Line length: **100 characters**
- Target: **Python 3.11**
- Imports are sorted by Ruff (`I` ruleset)

Run both tools before every commit:

```bash
make lint
make fmt
```

### UX/UI changes

Any change that affects commands, messages, keyboards, or interaction flows
**must follow** the guidelines in [`.github/copilot-instructions.md`](.github/copilot-instructions.md).

Key rules at a glance:

- Every main action needs a slash command **and** a keyboard button.
- Use `ReplyKeyboardMarkup` for persistent navigation (2–4 buttons max).
- Use `InlineKeyboardMarkup` only for context-specific decisions.
- Destructive actions require an explicit inline Confirm / Cancel step.
- Status messages must use `✅ ℹ️ ⚠️ ❌` icons consistently.

---

## Tests

Tests live in `tests/` and are run with pytest.

```bash
make test
```

- Unit tests must not require a live Telegram token or OpenAI key.
- Use `pytest` fixtures and mocks for external dependencies.
- Aim to cover any new logic with at least one happy-path and one error-path test.

---

## Submitting a pull request

- Keep pull requests focused: one feature or fix per PR.
- Fill in the PR description with **what** changed and **why**.
- Reference any related issue with `Closes #<issue-number>`.
- All CI checks must pass before merge.
- Maintainers may request changes; please respond promptly.

---

## Reporting bugs

Open an issue and include:

1. A clear title summarising the problem.
2. Steps to reproduce.
3. Expected behaviour vs. actual behaviour.
4. Relevant log output (redact any tokens or keys).
5. Python version and OS.

---

## Requesting features

Open an issue with the `enhancement` label and describe:

1. The problem you are trying to solve.
2. The proposed solution or behaviour.
3. Any alternative approaches you considered.
