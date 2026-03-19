.PHONY: test test-full coverage test-notebook build check publish-test publish clean

test:
	uv run pytest tests/ -v --tb=short

test-full:
	uv run tox

coverage:
	uv run pytest tests/ -v --cov=parawave --cov-report=term-missing

test-notebook:
	uv run pytest -p nbval --nbval notebooks/test_notebook.ipynb -v

build:
	uv run hatch build

check: build
	uv run twine check dist/*

publish-test: clean
	@echo "Building parawave-dev for TestPyPI..."
	sed -i.bak -e 's/^name = "parawave"/name = "parawave-dev"/' -e 's/parawave\[/parawave-dev\[/g' pyproject.toml; \
	trap 'mv pyproject.toml.bak pyproject.toml' EXIT; \
	uv run hatch build && \
	uv run twine upload --repository testpypi dist/*
	@echo "Published to TestPyPI as parawave-dev"

publish: clean
	@echo "Building parawave for PyPI..."
	uv run hatch build
	uv run twine upload dist/*
	@echo "Published to PyPI as parawave"

clean:
	rm -rf dist/ build/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
