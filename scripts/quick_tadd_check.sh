#!/bin/bash
# Quick TADD validation check

echo "🧪 Quick TADD Check"
echo "==================="

# Detect and run tests based on project type
if [ -f "pytest.ini" ] || [ -f "pyproject.toml" ]; then
    echo "Running pytest..."
    python3 -m pytest -x --tb=short --quiet 2>/dev/null || { echo "❌ Tests failed"; exit 1; }
elif [ -f "package.json" ] && grep -q '"test"' package.json; then
    echo "Running npm test..."
    npm test --silent 2>/dev/null || { echo "❌ Tests failed"; exit 1; }
elif [ -f "go.mod" ]; then
    echo "Running go test..."
    go test ./... -short 2>/dev/null || { echo "❌ Tests failed"; exit 1; }
else
    echo "⚠️ No test framework detected"
fi

echo "✅ Quick check passed!"
