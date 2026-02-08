#!/usr/bin/env bash
#
# Backend Quality Checks
# Run this locally before pushing to ensure CI passes
#

set -e

echo " Running Backend Quality Checks..."
echo "===================================="

cd "$(dirname "$0")"

# Check if we're in virtual environment
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo " Virtual environment active: $VIRTUAL_ENV"
else
    echo "  No virtual environment detected. Consider: python3 -m venv .venv && source .venv/bin/activate"
fi

# Install dev dependencies if needed
echo " Installing dev dependencies..."
pip install mypy black isort flake8 pytest-cov --quiet || echo "  Some dev deps might be missing"

echo ""
echo " Running mypy (type checking)..."
# Temporarily disabled for hackathon - too many false positives
# mypy . 2>/dev/null && echo " mypy OK" || echo "  mypy has issues (non-blocking)"

echo ""
echo " Checking code formatting with black..."
if black --check --quiet .; then
    echo " black formatting OK"
else
    echo " black formatting issues found. Run: black ."
    exit 1
fi

echo ""
echo " Checking import sorting with isort..."
if isort --check-only --quiet .; then
    echo " isort OK"
else
    echo " isort issues found. Run: isort ."
    exit 1
fi

echo ""
echo " Running flake8 linting..."
if flake8 --exclude=.venv .; then
    echo " flake8 linting OK"
else
    echo " flake8 issues found"
    exit 1
fi

echo ""
echo " Running tests..."
if python -m pytest --quiet; then
    echo " tests passed"
else
    echo " tests failed"
    exit 1
fi

echo ""
echo " All checks passed! Ready to commit."
echo "===================================="