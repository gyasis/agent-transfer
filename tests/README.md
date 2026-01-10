# Test Suite for Agent Transfer

Comprehensive automated pytest test suite for the selective import feature and core functionality.

## Test Structure

```
tests/
├── __init__.py                           # Test package marker
├── conftest.py                           # Shared fixtures and test configuration
├── test_import_analyzer.py               # Import analyzer module tests (30 tests)
├── test_selective_import_new.py          # Selective import flow tests (27 tests)
├── test_edge_cases_comprehensive.py      # Edge cases and error handling (27 tests)
└── README.md                             # This file
```

**Total: 84 automated tests**

## Test Categories

### 1. Import Analyzer Tests (`test_import_analyzer.py`)

Tests for the `import_analyzer.py` module:

**Archive Analysis** (6 tests)
- Successful archive analysis
- Agent counting (user vs project)
- Metadata extraction
- Empty archive handling
- Nonexistent archive error handling
- Corrupted archive error handling

**Agent Comparison** (4 tests)
- NEW agent detection
- IDENTICAL agent detection
- CHANGED agent detection
- None content handling

**Diff Generation** (5 tests)
- Addition detection
- Deletion detection
- Modification detection
- No changes detection
- Mixed changes detection

**Path Resolution** (4 tests)
- User agent path resolution
- Project agent path resolution
- Agent not found handling
- Invalid agent type handling

**Content Hashing** (3 tests)
- Hash consistency
- Different content produces different hashes
- Hash format validation

**Directory Scanning** (4 tests)
- Finding agents in directories
- Empty directory handling
- Nonexistent directory handling
- Invalid file handling

**Metadata Parsing** (4 tests)
- Successful metadata parsing
- Empty metadata file
- Malformed metadata
- Nonexistent metadata file

### 2. Selective Import Tests (`test_selective_import_new.py`)

Tests for selective import workflows:

**Import NEW Agents** (3 tests)
- File creation in correct directories
- Content preservation
- Statistics tracking

**Import CHANGED Agents** (4 tests)
- Overwrite mode (replaces content)
- Keep mode (preserves local)
- Duplicate mode (creates new file)
- Multiple duplicates handling

**Skip IDENTICAL Agents** (3 tests)
- IDENTICAL agent detection
- Default selection excludes IDENTICAL
- Statistics counting

**Import Statistics** (3 tests)
- All categories counted correctly
- User vs project separation
- Empty archive statistics

**Mixed Selections** (3 tests)
- NEW and CHANGED together
- Type preservation
- Partial selection

**Agent Name Filtering** (3 tests)
- Exact name matching
- Case sensitivity
- Nonexistent name handling

**Bulk Import** (2 tests)
- Bulk import all NEW agents
- Statistics tracking

**Type Preservation** (3 tests)
- User agent type preserved
- Project agent type preserved
- Type in comparisons

**Content Integrity** (3 tests)
- Frontmatter included
- Body included
- No corruption during comparison

### 3. Edge Case Tests (`test_edge_cases_comprehensive.py`)

Comprehensive edge case and error handling tests:

**Empty Archive** (2 tests)
- Appropriate messaging
- No errors raised

**Corrupted Archive** (2 tests)
- Error raised
- Clear error message

**Invalid Agent Names** (3 tests)
- Nonexistent name handling
- Special characters
- Empty name

**All IDENTICAL Scenario** (3 tests)
- Preview generation
- No import needed indication
- Statistics

**Missing Archive File** (2 tests)
- FileNotFoundError raised
- Clear error message

**Malformed Agent Files** (2 tests)
- Malformed YAML frontmatter
- Missing frontmatter

**Special Characters** (2 tests)
- Unicode characters
- Special YAML characters

**Large Archives** (1 test)
- Many agents (100+)

**Null/Empty Values** (4 tests)
- None full_content
- Empty description
- Empty tools list
- None tools list

**Path Edge Cases** (3 tests)
- Absolute vs relative paths
- Paths with spaces
- Very long paths

**Concurrent Operations** (1 test)
- Multiple archive analyses

**Permission Errors** (2 tests)
- Unreadable archive
- Write-protected directory

## Running Tests

### Run All Tests

```bash
uv run pytest tests/ -v
```

### Run Specific Test File

```bash
uv run pytest tests/test_import_analyzer.py -v
uv run pytest tests/test_selective_import_new.py -v
uv run pytest tests/test_edge_cases_comprehensive.py -v
```

### Run Specific Test Class

```bash
uv run pytest tests/test_import_analyzer.py::TestAnalyzeImportArchive -v
```

### Run Specific Test

```bash
uv run pytest tests/test_import_analyzer.py::TestAnalyzeImportArchive::test_analyze_import_archive_success -v
```

### Run with Coverage

```bash
# Install coverage tool (if not already installed)
uv pip install pytest-cov

# Run with coverage report
pytest tests/ --cov=agent_transfer --cov-report=term-missing

# Generate HTML coverage report
pytest tests/ --cov=agent_transfer --cov-report=html
# View report: open htmlcov/index.html
```

### Run Tests in Parallel

```bash
# Install pytest-xdist (if not already installed)
uv pip install pytest-xdist

# Run tests in parallel (faster)
pytest tests/ -n auto
```

## Fixtures

### Shared Fixtures (`conftest.py`)

**Directory Fixtures**
- `temp_dir` - Temporary directory for test isolation
- `local_agent_dir` - Local agent directory structure (user/project)

**Agent Fixtures**
- `sample_agent` - Basic test agent
- `sample_agent_modified` - Modified version of sample agent

**Archive Fixtures**
- `sample_archive` - Archive with user and project agents
- `empty_archive` - Archive with no agents
- `corrupted_archive` - Invalid tar.gz file

**Comparison Fixtures**
- `sample_comparison_new` - NEW agent comparison
- `sample_comparison_changed` - CHANGED agent comparison
- `sample_comparison_identical` - IDENTICAL agent comparison

**Preview Fixtures**
- `sample_preview` - Complete ImportPreview with mixed comparisons

## Test Patterns

### 1. Arrange-Act-Assert Pattern

```python
def test_analyze_import_archive_success(sample_archive):
    # Arrange - fixture provides sample archive

    # Act
    preview = analyze_import_archive(str(sample_archive))

    # Assert
    assert preview is not None
    assert len(preview.comparisons) >= 0
```

### 2. Test Isolation

Each test uses temporary directories and fixtures to ensure no shared state:

```python
def test_with_temp_dir(tmp_path):
    # tmp_path is a unique temporary directory for this test
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")
    # Cleanup is automatic
```

### 3. Exception Testing

```python
def test_corrupted_archive_raises_error(corrupted_archive):
    with pytest.raises(RuntimeError, match="corrupted"):
        analyze_import_archive(str(corrupted_archive))
```

### 4. Parametrized Tests

Tests can be parametrized for multiple scenarios:

```python
@pytest.mark.parametrize("status,expected_color", [
    ("NEW", "green"),
    ("CHANGED", "yellow"),
    ("IDENTICAL", "dim")
])
def test_status_colors(status, expected_color):
    assert STATUS_COLORS[status] == expected_color
```

## Best Practices

1. **Test Independence**: Each test is completely independent and can run in any order
2. **Fast Tests**: All tests complete in under 1 second
3. **Clear Names**: Test names describe what they test in plain English
4. **Single Assertion Focus**: Each test focuses on one specific behavior
5. **Edge Cases**: Comprehensive coverage of error conditions and boundary cases
6. **Fixture Reuse**: Common test data is defined in fixtures for DRY principle

## Adding New Tests

When adding new tests, follow this pattern:

```python
class TestNewFeature:
    """Test description for new feature."""

    def test_happy_path(self, relevant_fixture):
        """Test the normal, expected behavior."""
        # Arrange
        # Act
        # Assert
        pass

    def test_edge_case(self, relevant_fixture):
        """Test boundary conditions."""
        # Arrange
        # Act
        # Assert
        pass

    def test_error_handling(self):
        """Test error conditions."""
        with pytest.raises(ExpectedException):
            # Act that should raise
            pass
```

## Test Markers

Tests can be marked for selective execution:

```python
@pytest.mark.unit
def test_unit_level():
    """Unit test marker."""
    pass

@pytest.mark.integration
def test_integration_level():
    """Integration test marker."""
    pass

@pytest.mark.edge_case
def test_edge_case():
    """Edge case marker."""
    pass

@pytest.mark.slow
def test_slow_operation():
    """Slow test marker."""
    pass
```

Run specific markers:
```bash
pytest tests/ -m unit          # Run only unit tests
pytest tests/ -m "not slow"    # Skip slow tests
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    uv pip install -e ".[dev]"
    pytest tests/ -v --tb=short
```

## Coverage Goals

- **Line Coverage**: 85%+ for core modules
- **Branch Coverage**: 80%+ for conditional logic
- **Critical Paths**: 100% coverage for import/export flows

## Troubleshooting

**Tests fail with import errors**
```bash
# Ensure package is installed in development mode
uv pip install -e .
```

**Tests fail with fixture errors**
```bash
# Check conftest.py is present
ls tests/conftest.py
```

**Slow test execution**
```bash
# Run in parallel
pytest tests/ -n auto
```

**Permission errors on Linux**
```bash
# Some tests may require specific permissions
# Run with appropriate user permissions
```

## Contributing

When contributing tests:

1. Follow existing test structure and naming
2. Add docstrings to test classes and functions
3. Use fixtures for common test data
4. Test both happy paths and error cases
5. Keep tests fast and independent
6. Update this README with new test categories

## License

MIT License - Same as parent project
