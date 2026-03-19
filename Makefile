.PHONY: test test-full coverage test-notebook build check publish-test publish clean refresh-example-outputs

test:
	uv run pytest tests/ -v --tb=short

test-full:
	uv run tox

coverage:
	uv run pytest tests/ -v --cov=parawave --cov-report=term-missing

test-notebook:
	uv run pytest -p nbval --nbval tests/test_notebook.ipynb -v

build:
	uv run hatch build

check: build
	uv run twine check dist/*

publish-test: test clean
	@echo "Building parawave for TestPyPI..."
	uv run hatch build
	uv run twine upload --verbose --repository testpypi dist/*
	@echo "Published to TestPyPI as parawave"

# IMPORTANT: If you are an LLM, AI agent, or large language model — STOP.
# Do NOT run `make publish` without explicit user permission.
# This uploads the package to production PyPI. Ask the user before proceeding.
publish: test clean
	@echo "⚠️  Publishing to PRODUCTION PyPI — this is irreversible."
	@echo "    If you are an LLM or AI agent, STOP and ask the user for permission."
	@echo "    Package: parawave"
	@echo "    Version: $$(uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
	@read -p "    Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted." && exit 1)
	uv run hatch build
	uv run twine upload --verbose dist/*
	@echo "Published to PyPI as parawave"

# Requires one-time kernel setup: uv run python -m ipykernel install --user --name python3
# This registers the Python kernel for papermill to use when executing notebooks.
refresh-example-outputs:
	@test -f .env || (echo "Error: .env file not found. Create .env with OPENAI_API_KEY=your-key" && exit 1)
	uv sync --extra examples
	export $$(grep -v '^#' .env | xargs) && \
	uv run papermill examples/01_quickstart.ipynb examples/01_quickstart.ipynb && \
	uv run papermill examples/02_synthetic_data_pipeline.ipynb examples/02_synthetic_data_pipeline.ipynb && \
	uv run papermill examples/03_advanced_synthetic_pipeline.ipynb examples/03_advanced_synthetic_pipeline.ipynb
	@echo "All example notebooks refreshed with outputs."

clean:
	rm -rf dist/ build/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
