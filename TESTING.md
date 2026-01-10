# Testing Guide for Agent Transfer

Quick reference for running and managing the test suite.

## Quick Start

```bash
# Install test dependencies
uv pip install -e ".[dev]"

# Run all tests
uv run pytest tests/ -v

# Run with short traceback
uv run pytest tests/ -v --tb=short
```

## Test Suite Overview

- **84 total tests** across 3 test files
- **30 tests** for import analyzer module
- **27 tests** for selective import flows
- **27 tests** for edge cases and error handling
- All tests pass in under 1 second

## Common Commands

### Run Specific Test Files

```bash
# Import analyzer tests only
uv run pytest tests/test_import_analyzer.py -v

# Selective import tests only
uv run pytest tests/test_selective_import_new.py -v

# Edge case tests only
uv run pytest tests/test_edge_cases_comprehensive.py -v
```

### Run Specific Test Classes

```bash
# Run all tests in a class
uv run pytest tests/test_import_analyzer.py::TestAnalyzeImportArchive -v

# Run all comparison tests
uv run pytest tests/test_import_analyzer.py::TestCompareAgents -v
```

### Run Specific Tests

```bash
# Run single test by name
uv run pytest tests/test_import_analyzer.py::TestAnalyzeImportArchive::test_analyze_import_archive_success -v
```

### Run Tests Matching Pattern

```bash
# Run all tests with "archive" in name
uv run pytest tests/ -k archive -v

# Run all tests with "changed" in name
uv run pytest tests/ -k changed -v

# Run tests NOT matching pattern
uv run pytest tests/ -k "not slow" -v
```

## Test Output Options

### Verbose Mode

```bash
# Show test names and pass/fail
pytest tests/ -v

# Show very verbose output (more details)
pytest tests/ -vv
```

### Traceback Options

```bash
# Short traceback (recommended)
pytest tests/ --tb=short

# No traceback
pytest tests/ --tb=no

# Line-only traceback
pytest tests/ --tb=line

# Full traceback
pytest tests/ --tb=long
```

### Stop on First Failure

```bash
# Stop after first failure
pytest tests/ -x

# Stop after N failures
pytest tests/ --maxfail=3
```

### Show Print Statements

```bash
# Show print() output even for passing tests
pytest tests/ -s

# Show print() only for failed tests (default)
pytest tests/
```

## Coverage Analysis

### Generate Coverage Report

```bash
# Terminal report
pytest tests/ --cov=agent_transfer --cov-report=term-missing

# HTML report (view in browser)
pytest tests/ --cov=agent_transfer --cov-report=html
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Coverage Configuration

Coverage settings are in `pytest.ini`:
- Source: `agent_transfer` package
- Omits: tests, venv, __pycache__
- Precision: 2 decimal places
- Shows missing lines

## Performance Testing

### Run Tests in Parallel

```bash
# Install xdist
uv pip install pytest-xdist

# Auto-detect CPU cores
pytest tests/ -n auto

# Use specific number of workers
pytest tests/ -n 4
```

### Show Slowest Tests

```bash
# Show 10 slowest tests
pytest tests/ --durations=10

# Show all test durations
pytest tests/ --durations=0
```

## Test Development

### Run Tests in Watch Mode

```bash
# Install pytest-watch
uv pip install pytest-watch

# Watch for changes and re-run
ptw tests/
```

### Run Only Failed Tests

```bash
# Run tests that failed last time
pytest tests/ --lf

# Run failed first, then others
pytest tests/ --ff
```

### Create New Test

```bash
# Create test file in tests/ directory
touch tests/test_new_feature.py
```

Example test template:
```python
"""Tests for new feature."""
import pytest
from agent_transfer.module import function

class TestNewFeature:
    """Test new feature functionality."""

    def test_happy_path(self):
        """Test normal operation."""
        result = function()
        assert result is not None

    def test_edge_case(self):
        """Test boundary condition."""
        with pytest.raises(ValueError):
            function(invalid_input)
```

## Debugging Tests

### Run with PDB on Failure

```bash
# Drop into debugger on failure
pytest tests/ --pdb

# Drop into debugger on first failure
pytest tests/ -x --pdb
```

### Show Local Variables

```bash
# Show local variables in tracebacks
pytest tests/ -l

# Show very verbose locals
pytest tests/ -vv -l
```

### Run Single Test with Full Output

```bash
pytest tests/test_import_analyzer.py::TestAnalyzeImportArchive::test_analyze_import_archive_success -vv -s
```

## Test Markers

### Available Markers

- `unit` - Unit tests for individual functions
- `integration` - Integration tests for workflows
- `edge_case` - Edge case and error handling
- `slow` - Tests that take significant time

### Run Tests by Marker

```bash
# Run only unit tests
pytest tests/ -m unit

# Run only integration tests
pytest tests/ -m integration

# Run all except slow tests
pytest tests/ -m "not slow"

# Combine markers (AND)
pytest tests/ -m "unit and edge_case"

# Combine markers (OR)
pytest tests/ -m "unit or integration"
```

### Mark Your Tests

```python
@pytest.mark.unit
def test_something():
    pass

@pytest.mark.slow
@pytest.mark.integration
def test_slow_integration():
    pass
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e ".[dev]"
      - name: Run tests
        run: |
          pytest tests/ -v --tb=short
```

## Test Fixtures

### Common Fixtures (from conftest.py)

- `temp_dir` - Temporary directory
- `sample_agent` - Test agent
- `sample_archive` - Test archive
- `empty_archive` - Empty archive
- `corrupted_archive` - Invalid archive
- `local_agent_dir` - Agent directory structure

### Using Fixtures

```python
def test_with_fixture(sample_agent):
    # Fixture automatically provided
    assert sample_agent.name == "test-agent"
```

### Create Custom Fixtures

```python
@pytest.fixture
def custom_fixture():
    # Setup
    data = create_test_data()
    yield data
    # Teardown
    cleanup_test_data(data)
```

## Troubleshooting

### Import Errors

```bash
# Ensure package is installed
uv pip install -e .

# Check Python path
python -c "import agent_transfer; print(agent_transfer.__file__)"
```

### Fixture Not Found

```bash
# Verify conftest.py exists
ls tests/conftest.py

# Check fixture is defined in conftest.py or test file
grep -r "@pytest.fixture" tests/
```

### Tests Not Discovered

```bash
# Check test discovery patterns
pytest --collect-only tests/

# Verify test file naming (must start with test_)
ls tests/test_*.py
```

### Permission Errors

```bash
# Some tests create files - ensure write permissions
chmod +w tests/

# Run with appropriate user
```

## Best Practices

1. **Run tests before committing**: `pytest tests/ --tb=short`
2. **Write tests for new features**: Follow existing patterns
3. **Keep tests fast**: Use mocks for slow operations
4. **Test edge cases**: Don't just test happy paths
5. **Use fixtures**: Reuse common test data
6. **Clear test names**: Describe what you're testing
7. **One assertion per test**: Focus on single behavior

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [pytest parametrize](https://docs.pytest.org/en/stable/parametrize.html)
- [pytest-cov](https://pytest-cov.readthedocs.io/)

## Getting Help

```bash
# Show pytest help
pytest --help

# Show available fixtures
pytest --fixtures

# Show available markers
pytest --markers
```

For project-specific help, see `tests/README.md` for detailed test suite documentation.
