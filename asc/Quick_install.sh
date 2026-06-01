#!/bin/bash
# Quick-start script for Tom's AI system on Linux
# Extracts, verifies requirements, and guides installation

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 Tom's AI System - Linux Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if archive is provided
if [ ! -f "toms_ai_tar.gz" ]; then
    echo -e "${RED}✗ Error: toms_ai_tar.gz not found in current directory${NC}"
    echo ""
    echo "Please place the archive in this directory and run again."
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check requirements
echo "📋 Checking requirements..."
echo ""

MISSING_DEPS=()

# Check Claude Code
if command_exists claude; then
    echo -e "${GREEN}✓ Claude Code CLI found${NC}"
else
    echo -e "${YELLOW}⚠ Claude Code CLI not found${NC}"
    MISSING_DEPS+=("claude")
fi

# Check Git
if command_exists git; then
    echo -e "${GREEN}✓ Git found${NC}"
else
    echo -e "${RED}✗ Git not found${NC}"
    MISSING_DEPS+=("git")
fi

# Check Python
if command_exists python3; then
    PY_VERSION=$(python3 --version | cut -d' ' -f2)
    echo -e "${GREEN}✓ Python found (${PY_VERSION})${NC}"
else
    echo -e "${RED}✗ Python3 not found${NC}"
    MISSING_DEPS+=("python3")
fi

# Check uv
if command_exists uv; then
    echo -e "${GREEN}✓ uv package manager found${NC}"
else
    echo -e "${YELLOW}⚠ uv not found (needed for MCP Agent Mail)${NC}"
    MISSING_DEPS+=("uv")
fi

# Check Go
if command_exists go; then
    GO_VERSION=$(go version | awk '{print $3}' | sed 's/go//')
    echo -e "${GREEN}✓ Go found (${GO_VERSION})${NC}"
else
    echo -e "${YELLOW}⚠ Go not found (needed for Super Claude Kit tools)${NC}"
    MISSING_DEPS+=("go")
fi

# Check Redis (optional)
if command_exists redis-cli; then
    echo -e "${GREEN}✓ Redis found (optional)${NC}"
else
    echo -e "${BLUE}ℹ Redis not found (optional for MCP Agent Mail)${NC}"
fi

echo ""

# Handle missing dependencies
if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}Missing dependencies:${NC}"
    echo ""
    
    for dep in "${MISSING_DEPS[@]}"; do
        case $dep in
            claude)
                echo "• Claude Code CLI"
                echo "  Install: https://docs.anthropic.com/en/docs/build-with-claude/claude-code"
                echo ""
                ;;
            git)
                echo "• Git"
                echo "  Install: sudo apt install git"
                echo ""
                ;;
            python3)
                echo "• Python 3"
                echo "  Install: sudo apt install python3 python3-pip"
                echo ""
                ;;
            uv)
                echo "• uv package manager"
                echo "  Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
                echo "  Then: export PATH=\"\$HOME/.local/bin:\$PATH\""
                echo ""
                ;;
            go)
                echo "• Go 1.23+"
                echo "  Install: sudo apt install golang-go"
                echo "  Or: https://go.dev/dl/"
                echo ""
                ;;
        esac
    done
    
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Install missing dependencies and run this script again."
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Extract archive
echo ""
echo "📦 Extracting archive..."
tar -xzf toms_ai_tar.gz
echo -e "${GREEN}✓ Archive extracted${NC}"
echo ""

# Prompt for installation location
echo "📁 Choose installation method:"
echo ""
echo "1) Install to current directory ($(pwd))"
echo "2) Install to ~/ai-workspace/"
echo "3) Specify custom location"
echo ""
read -p "Choice (1-3): " install_choice

case $install_choice in
    1)
        INSTALL_ROOT="$(pwd)"
        ;;
    2)
        INSTALL_ROOT="$HOME/ai-workspace"
        mkdir -p "$INSTALL_ROOT"
        mv "Tom's AI" "$INSTALL_ROOT/"
        ;;
    3)
        read -p "Enter installation path: " custom_path
        INSTALL_ROOT="$custom_path"
        mkdir -p "$INSTALL_ROOT"
        mv "Tom's AI" "$INSTALL_ROOT/"
        ;;
    *)
        echo "Invalid choice. Using current directory."
        INSTALL_ROOT="$(pwd)"
        ;;
esac

cd "$INSTALL_ROOT/Tom's AI"
echo -e "${GREEN}✓ Installation location: $INSTALL_ROOT/Tom's AI${NC}"
echo ""

# Install Super Claude Kit
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Installing Super Claude Kit"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd super-claude-kit

if command_exists go; then
    echo "Running installer..."
    bash install
    echo ""
    echo -e "${GREEN}✓ Super Claude Kit installed${NC}"
else
    echo -e "${YELLOW}⚠ Skipping Super Claude Kit (Go not found)${NC}"
fi

echo ""

# Install MCP Agent Mail
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📧 Installing MCP Agent Mail"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd ../mcp_agent_mail

if command_exists uv && command_exists python3; then
    echo "Setting up Python environment..."
    
    # Check if Python 3.14 is available
    if uv python list | grep -q "3.14"; then
        uv python install 3.14
        uv venv -p 3.14
    else
        echo -e "${YELLOW}⚠ Python 3.14 not available, using system Python${NC}"
        uv venv
    fi
    
    source .venv/bin/activate
    
    echo "Installing dependencies..."
    uv sync
    
    echo ""
    echo "Detecting and integrating with coding agents..."
    bash scripts/automatically_detect_all_installed_coding_agents_and_install_mcp_agent_mail_in_all.sh
    
    echo ""
    echo -e "${GREEN}✓ MCP Agent Mail installed${NC}"
    
    # Offer to start server
    echo ""
    read -p "Start MCP Agent Mail server now? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Starting server on port 8765..."
        bash scripts/run_server_with_token.sh &
        SERVER_PID=$!
        echo -e "${GREEN}✓ Server started (PID: $SERVER_PID)${NC}"
        echo ""
        echo "To stop: kill $SERVER_PID"
        echo "To restart later: bash scripts/run_server_with_token.sh"
    fi
else
    echo -e "${YELLOW}⚠ Skipping MCP Agent Mail (uv or python3 not found)${NC}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 Installation location:"
echo "   $INSTALL_ROOT/Tom's AI"
echo ""
echo "🚀 Quick Start:"
echo ""
echo "1. Test Super Claude Kit:"
echo "   cd super-claude-kit"
echo "   bash scripts/select-worker.sh --list"
echo ""
echo "2. Launch a worker:"
echo "   bash scripts/select-worker.sh"
echo ""
echo "3. Create custom worker profiles:"
echo "   mkdir -p ~/.claude/workers"
echo "   # Add .md files with worker configurations"
echo ""
echo "4. Multi-agent workflow:"
echo "   # Terminal 1:"
echo "   bash scripts/select-worker.sh backend"
echo ""
echo "   # Terminal 2:"
echo "   bash scripts/select-worker.sh frontend"
echo ""
if command_exists uv && command_exists python3; then
    echo "5. Check MCP Agent Mail:"
    echo "   curl http://localhost:8765/health"
    echo ""
fi
echo "📚 Documentation:"
echo "   See linux_migration_analysis.md for detailed usage"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
