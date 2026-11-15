.PHONY: install lint typecheck test pareto montecarlo verify ui-build serve

UV ?= uv

install:
	$(UV) sync --all-extras

lint:
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

typecheck:
	$(UV) run mypy src

test:
	$(UV) run pytest --cov=chronos_mesh --cov-fail-under=95 --cov-report=term-missing

pareto:
	$(UV) run chronos pareto --disruption red_sea_and_kaohsiung_compound

montecarlo:
	$(UV) run chronos montecarlo --trials 500

ui-build:
	cd ui && npm install && npm run build

verify: lint typecheck test pareto montecarlo

serve:
	$(UV) run chronos serve --host 127.0.0.1 --port 8010
