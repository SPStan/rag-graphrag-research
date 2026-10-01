UV ?= uv
UV_PROJECT_ENVIRONMENT ?= .venv-check
export UV_PROJECT_ENVIRONMENT

.PHONY: check
check:
	$(UV) run --locked python -m scripts.check
