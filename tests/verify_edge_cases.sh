#!/bin/bash
# Comprehensive edge case verification script

echo "=================================================="
echo "Edge Case Verification Script"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

# Test 1: Empty Archive
echo -e "${YELLOW}Test 1: Empty Archive${NC}"
echo "---------------------------------------"
python tests/test_edge_cases.py 2>&1 | grep -q "Empty archive handled correctly"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ PASSED${NC} - Empty archive detection works"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC} - Empty archive test failed"
    ((FAILED++))
fi
echo ""

# Test 2: Corrupted Archive
echo -e "${YELLOW}Test 2: Corrupted Archive${NC}"
echo "---------------------------------------"
python tests/test_edge_cases.py 2>&1 | grep -q "Corrupted archive error"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ PASSED${NC} - Corrupted archive error handling works"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC} - Corrupted archive test failed"
    ((FAILED++))
fi
echo ""

# Test 3: All Identical
echo -e "${YELLOW}Test 3: All Identical Agents${NC}"
echo "---------------------------------------"
python tests/test_all_identical.py 2>&1 | grep -q "All identical condition detected correctly"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ PASSED${NC} - All identical detection works"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC} - All identical test failed"
    ((FAILED++))
fi
echo ""

# Summary
echo "=================================================="
echo "Test Summary"
echo "=================================================="
echo -e "Passed: ${GREEN}${PASSED}${NC}"
echo -e "Failed: ${RED}${FAILED}${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All edge case tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
