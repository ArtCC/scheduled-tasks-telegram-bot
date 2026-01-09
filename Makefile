PYTHON := python3
VENV := .venv
ACTIVATE := source $(VENV)/bin/activate

.PHONY: venv install lint fmt test run

venv:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip

install: venv
	$(ACTIVATE) && pip install -r requirements-dev.txt

lint:
	$(ACTIVATE) && ruff check .

fmt:
	$(ACTIVATE) && black .

test:
	$(ACTIVATE) && pytest

run:
	$(ACTIVATE) && $(PYTHON) -m scheduled_bot
