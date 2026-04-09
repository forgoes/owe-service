PYTHON ?= $(shell command -v python 2>/dev/null || command -v python3)

.PHONY: pip pip-update test eval migrate upgrade downgrade revision

pip:
	$(PYTHON) -m pip install --no-build-isolation -e ".[dev]"

pip-update:
	$(PYTHON) -m pip install --no-build-isolation --upgrade -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

eval:
	$(PYTHON) -m app.evals.run_qualification_eval

migrate:
	alembic revision --autogenerate -m "$(m)"

upgrade:
	alembic upgrade head

downgrade:
	alembic downgrade -1

revision:
	alembic revision -m "$(m)"
