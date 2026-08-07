UV ?= uv

.PHONY: sync check lock-check test lint security audit docker

sync:
	$(UV) sync --all-groups

check: lock-check lint security test audit

lock-check:
	$(UV) lock --check

test:
	$(UV) run --locked --no-sync pytest -q

lint:
	$(UV) run --locked --no-sync ruff check .

security:
	$(UV) run --locked --no-sync bandit -r app.py worker.py core routers -q -ll

audit:
	UV=$(UV) ./scripts/audit_dependencies.sh

docker:
	docker build --tag huawei-health-export-tool:local .
