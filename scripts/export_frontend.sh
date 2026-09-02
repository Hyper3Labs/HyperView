#!/bin/bash
# Export frontend to static files for Python package

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
HYPER_SCATTER_DIR="$PROJECT_ROOT/hyper-scatter"
STATIC_DIR="$PROJECT_ROOT/src/hyperview/server/static"

# Build hyper-scatter library if it's a local checkout
if [ -d "$HYPER_SCATTER_DIR" ] && [ -f "$HYPER_SCATTER_DIR/package.json" ]; then
    echo "Building hyper-scatter library..."
    cd "$HYPER_SCATTER_DIR"
    if [ ! -d "node_modules" ]; then
        npm install
    fi
    npm run build:lib
fi

echo "Building frontend..."
cd "$FRONTEND_DIR"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Build for static export
npm run build

# Copy to Python package
echo "Copying build output into Python package..."
rm -rf "$STATIC_DIR"
mkdir -p "$STATIC_DIR"
cp -r out/* "$STATIC_DIR/"

# The packaged panel SDK contract is read by panel linters, so refresh it from
# the same source the shell was just built from.
echo "Refreshing the packaged panel SDK surface..."
cd "$PROJECT_ROOT"
python3 scripts/emit_panel_sdk_surface.py

echo ""
echo "✅ Frontend exported to $STATIC_DIR"
echo ""
echo "To test, run:"
echo "  cd $PROJECT_ROOT"
echo "  uv run hyperview serve"
