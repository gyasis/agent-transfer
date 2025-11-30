#!/bin/bash
# Automatic installation script using uv for isolated environment

set -e

echo "🚀 Installing agent-transfer with uv (isolated environment)"
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed"
    echo ""
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo ""
    echo "✅ uv installed! Please restart your terminal or run:"
    echo "   source ~/.cargo/env  # or add to your PATH"
    echo ""
    exit 1
fi

echo "✅ uv found: $(which uv)"
echo ""

# Install in isolated environment
echo "📦 Installing agent-transfer package..."
uv pip install -e .

echo ""
echo "✅ Installation complete!"
echo ""
echo "You can now use:"
echo "  agent-transfer export"
echo "  agent-transfer import backup.tar.gz"
echo "  agent-transfer discover"
echo ""
echo "Dependencies are isolated - your Python environment is clean! 🎉"

