from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_nginx_example_contains_phase_zero_resource_limits():
    config = (PROJECT_ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")

    assert "client_max_body_size 2g;" in config
    assert "limit_conn per_ip 2;" in config
    assert "limit_req zone=parse_rate" in config
    assert "proxy_request_buffering off;" in config
    assert "proxy_read_timeout 1800s;" in config


def test_ci_covers_supported_python_versions_and_security_gates():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert 'python-version: ["3.11", "3.12"]' in workflow
    assert "ruff check ." in workflow
    assert "bandit -r app.py worker.py core routers" in workflow
    assert "make audit" in workflow
    assert "docker build" in workflow
