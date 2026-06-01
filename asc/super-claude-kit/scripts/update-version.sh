#!/bin/bash
# Update version strings across all files
# Usage: ./scripts/update-version.sh <new-version>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

NEW_VERSION="$1"

if [ -z "$NEW_VERSION" ]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 v1.0.0"
  exit 1
fi

# Remove 'v' prefix if present for some files
VERSION_NO_V="${NEW_VERSION#v}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Updating Version to $NEW_VERSION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$ROOT_DIR"

# 1. Update manifest.json
echo "Updating manifest.json..."
if [ -f "manifest.json" ]; then
  sed -i '' "s/\"version\": \".*\"/\"version\": \"$VERSION_NO_V\"/" manifest.json
  echo "✅ manifest.json"
fi

# 2. Update README.md badge
echo "Updating README.md..."
if [ -f "README.md" ]; then
  sed -i '' "s/version-[0-9.]*-blue/version-$VERSION_NO_V-blue/" README.md
  echo "✅ README.md"
fi

# 3. Update install script default version
echo "Updating install script..."
if [ -f "install" ]; then
  sed -i '' "s/VERSION=\"\${VERSION:-v[0-9.]*}\"/VERSION=\"\${VERSION:-$NEW_VERSION}\"/" install
  echo "✅ install"
fi

# 4. Update dependency-scanner version
echo "Updating dependency-scanner..."
if [ -f "tools/dependency-scanner/main.go" ]; then
  sed -i '' "s/Dependency Scanner v[0-9.]*/Dependency Scanner $NEW_VERSION/" tools/dependency-scanner/main.go
  echo "✅ tools/dependency-scanner/main.go"
fi

# 5. Update progressive-reader version
echo "Updating progressive-reader..."
if [ -f "tools/progressive-reader/cmd/main.go" ]; then
  sed -i '' "s/const version = \"[v0-9.]*\"/const version = \"$VERSION_NO_V\"/" tools/progressive-reader/cmd/main.go
  echo "✅ tools/progressive-reader/cmd/main.go"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Version Updated to $NEW_VERSION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Modified files:"
echo "  - manifest.json"
echo "  - README.md"
echo "  - install"
echo "  - tools/dependency-scanner/main.go"
echo "  - tools/progressive-reader/cmd/main.go"
echo ""
echo "⚠️  Remember to rebuild binaries: ./scripts/build-all-binaries.sh"
