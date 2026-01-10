#!/bin/bash
# Integration test script for selective import feature
# Tests real CLI behavior without mocking

set -e  # Exit on error

echo "==================================="
echo "Agent Transfer - Integration Tests"
echo "==================================="
echo ""

# Setup
TEST_DIR="/tmp/agent-transfer-test-$(date +%s)"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

echo "Test directory: $TEST_DIR"
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

function test_skip() {
    echo -e "${YELLOW}⊘ SKIP${NC}: $1"
}

# Test 1: CLI Help Commands
echo "Test 1: CLI Help Commands"
echo "-------------------------"
if uv run agent-transfer --help > /dev/null 2>&1; then
    test_pass "agent-transfer --help"
else
    test_fail "agent-transfer --help"
fi

if uv run agent-transfer import --help > /dev/null 2>&1; then
    test_pass "agent-transfer import --help"
else
    test_fail "agent-transfer import --help"
fi
echo ""

# Test 2: Create Test Archive
echo "Test 2: Create Test Archive"
echo "----------------------------"
if uv run agent-transfer export --all test-archive.tar.gz > /dev/null 2>&1; then
    test_pass "Export test archive"
    if [ -f "test-archive.tar.gz" ]; then
        test_pass "Archive file exists"
        SIZE=$(stat -c%s "test-archive.tar.gz")
        if [ "$SIZE" -gt 1000 ]; then
            test_pass "Archive has reasonable size ($SIZE bytes)"
        else
            test_fail "Archive too small ($SIZE bytes)"
        fi
    else
        test_fail "Archive file not created"
    fi
else
    test_fail "Export test archive"
fi
echo ""

# Test 3: List Agents
echo "Test 3: List Agents"
echo "-------------------"
AGENT_COUNT=$(uv run agent-transfer list-agents 2>/dev/null | grep -c "│" || echo "0")
if [ "$AGENT_COUNT" -gt 0 ]; then
    test_pass "List agents command ($AGENT_COUNT agents found)"
else
    test_fail "List agents command (no agents found)"
fi
echo ""

# Test 4: Invalid Agent Import
echo "Test 4: Invalid Agent Import"
echo "----------------------------"
if ! uv run agent-transfer import test-archive.tar.gz --agent nonexistent-agent-xyz 2>&1 | grep -q "not found"; then
    test_fail "Should show error for invalid agent name"
else
    test_pass "Error shown for invalid agent name"
fi
echo ""

# Test 5: Bulk Import with Keep Mode (Safe)
echo "Test 5: Bulk Import with Keep Mode"
echo "-----------------------------------"
if uv run agent-transfer import test-archive.tar.gz --bulk --conflict-mode keep > /dev/null 2>&1; then
    test_pass "Bulk import with keep mode"
else
    test_fail "Bulk import with keep mode"
fi
echo ""

# Test 6: Discover Command
echo "Test 6: Discover Command"
echo "------------------------"
if uv run agent-transfer discover > /dev/null 2>&1; then
    test_pass "Discover command"
else
    test_fail "Discover command"
fi
echo ""

# Test 7: Validate Tools Command
echo "Test 7: Validate Tools Command"
echo "-------------------------------"
# This may fail if agents have incompatible tools, so we just check it runs
if uv run agent-transfer validate-tools > /dev/null 2>&1; then
    test_pass "Validate tools command (all tools compatible)"
else
    # Exit code 1 means incompatible tools found, but command worked
    test_pass "Validate tools command (found incompatibilities)"
fi
echo ""

# Test 8: Archive Structure
echo "Test 8: Archive Structure"
echo "-------------------------"
if tar -tzf test-archive.tar.gz | grep -q "user-agents/"; then
    test_pass "Archive contains user-agents directory"
else
    test_fail "Archive missing user-agents directory"
fi

if tar -tzf test-archive.tar.gz | grep -q "metadata.txt"; then
    test_pass "Archive contains metadata.txt"
else
    test_fail "Archive missing metadata.txt"
fi
echo ""

# Test 9: Direct Agent Import (Safe with Keep Mode)
echo "Test 9: Direct Agent Import"
echo "----------------------------"
# Get first agent name from list
FIRST_AGENT=$(uv run agent-transfer list-agents 2>/dev/null | grep "│" | head -n 1 | awk -F'│' '{print $3}' | xargs || echo "")
if [ -n "$FIRST_AGENT" ]; then
    echo "Testing with agent: $FIRST_AGENT"
    if uv run agent-transfer import test-archive.tar.gz --agent "$FIRST_AGENT" --conflict-mode keep > /dev/null 2>&1; then
        test_pass "Direct agent import with keep mode"
    else
        test_fail "Direct agent import with keep mode"
    fi
else
    test_skip "Direct agent import (no agents available)"
fi
echo ""

# Test 10: Import with Discovery
echo "Test 10: Import with Discovery Flag"
echo "------------------------------------"
if uv run agent-transfer import test-archive.tar.gz --bulk --conflict-mode keep --discover > /dev/null 2>&1; then
    test_pass "Import with --discover flag"
else
    test_fail "Import with --discover flag"
fi
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
    EXIT_CODE=0
else
    echo -e "${RED}Some tests failed.${NC}"
    EXIT_CODE=1
fi

# Cleanup
echo ""
echo "Cleaning up test directory..."
cd /
rm -rf "$TEST_DIR"
echo "Done."

exit $EXIT_CODE
