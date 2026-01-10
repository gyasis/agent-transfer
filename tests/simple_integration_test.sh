#!/bin/bash
# Simple integration test for selective import feature
# Run from project root: bash tests/simple_integration_test.sh

set -e  # Exit on error

echo "==================================="
echo "Agent Transfer - Integration Tests"
echo "==================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

function test_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASS_COUNT++))
}

function test_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAIL_COUNT++))
}

# Test 1: CLI Help
echo "Test 1: CLI Help Commands"
echo "-------------------------"
uv run agent-transfer --help > /dev/null 2>&1 && test_pass "Main help" || test_fail "Main help"
uv run agent-transfer import --help > /dev/null 2>&1 && test_pass "Import help" || test_fail "Import help"
echo ""

# Test 2: List Agents
echo "Test 2: List Agents"
echo "-------------------"
AGENT_LIST=$(uv run agent-transfer list-agents 2>/dev/null)
if echo "$AGENT_LIST" | grep -q "Total:"; then
    test_pass "List agents command"
else
    test_fail "List agents command"
fi
echo ""

# Test 3: Create Archive
echo "Test 3: Export Archive"
echo "----------------------"
if [ -f "test-archive.tar.gz" ]; then
    echo "Using existing test-archive.tar.gz"
    test_pass "Archive exists"
else
    uv run agent-transfer export --all test-archive.tar.gz > /dev/null 2>&1 && test_pass "Export archive" || test_fail "Export archive"
fi
echo ""

# Test 4: Invalid Agent Import
echo "Test 4: Invalid Agent Name"
echo "--------------------------"
OUTPUT=$(uv run agent-transfer import test-archive.tar.gz --agent nonexistent-xyz-123 2>&1 || true)
if echo "$OUTPUT" | grep -q "not found"; then
    test_pass "Error for invalid agent"
else
    test_fail "Error for invalid agent"
fi
echo ""

# Test 5: Bulk Import (Safe with Keep)
echo "Test 5: Bulk Import (Keep Mode)"
echo "--------------------------------"
uv run agent-transfer import test-archive.tar.gz --bulk --conflict-mode keep > /dev/null 2>&1 && test_pass "Bulk import" || test_fail "Bulk import"
echo ""

# Test 6: Validate Tools
echo "Test 6: Validate Tools"
echo "----------------------"
# May exit with 1 if incompatible tools found, but that's ok
uv run agent-transfer validate-tools > /dev/null 2>&1
if [ $? -eq 0 ]; then
    test_pass "Validate tools (all compatible)"
elif [ $? -eq 1 ]; then
    test_pass "Validate tools (found incompatibilities)"
else
    test_fail "Validate tools (unexpected error)"
fi
echo ""

# Test 7: Discover
echo "Test 7: Discover Installation"
echo "------------------------------"
uv run agent-transfer discover > /dev/null 2>&1 && test_pass "Discover command" || test_fail "Discover command"
echo ""

# Summary
echo ""
echo "==================================="
echo "Test Summary"
echo "==================================="
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
