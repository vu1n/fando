#!/usr/bin/env bash
#
# install.sh - Setup script for Matryoshka MCP integration
#
# Detects bunx/npx, validates Matryoshka installation, and configures
# Claude Code MCP settings for fando-plan token optimization.
#
# Usage:
#   ./scripts/install.sh
#   ./scripts/install.sh --check    # Check current status without modifying
#   ./scripts/install.sh --uninstall # Remove Matryoshka MCP config
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SETTINGS_FILE="$PROJECT_ROOT/.claude/settings.local.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

detect_package_runner() {
    # Prefer bunx (faster, Bun's package runner)
    if command -v bunx &>/dev/null; then
        echo "bunx"
        return 0
    fi

    # Fall back to npx
    if command -v npx &>/dev/null; then
        echo "npx"
        return 0
    fi

    return 1
}

get_mcp_config() {
    local runner="$1"

    if [ "$runner" = "bunx" ]; then
        cat <<'EOF'
{
  "command": "bunx",
  "args": ["matryoshka-rlm"]
}
EOF
    else
        cat <<'EOF'
{
  "command": "npx",
  "args": ["-y", "matryoshka-rlm"]
}
EOF
    fi
}

test_matryoshka() {
    local runner="$1"
    local args=""

    if [ "$runner" = "npx" ]; then
        args="-y"
    fi

    echo "Testing Matryoshka installation..."

    # Try to get version (quick validation)
    if $runner $args matryoshka-rlm --version &>/dev/null 2>&1; then
        return 0
    fi

    # Package might need to be installed
    echo "Installing matryoshka-rlm package..."
    if [ "$runner" = "bunx" ]; then
        bun add -g matryoshka-rlm &>/dev/null 2>&1 || true
    else
        npm install -g matryoshka-rlm &>/dev/null 2>&1 || true
    fi

    # Try again
    if $runner $args matryoshka-rlm --version &>/dev/null 2>&1; then
        return 0
    fi

    return 1
}

merge_settings() {
    local runner="$1"
    local mcp_config
    mcp_config=$(get_mcp_config "$runner")

    # Ensure .claude directory exists
    mkdir -p "$PROJECT_ROOT/.claude"

    if [ -f "$SETTINGS_FILE" ]; then
        # Merge into existing settings using jq or python
        if command -v jq &>/dev/null; then
            # Use jq for JSON manipulation
            local temp_file
            temp_file=$(mktemp)

            jq --argjson mcp "$mcp_config" '
                .mcpServers = (.mcpServers // {}) |
                .mcpServers.matryoshka = $mcp
            ' "$SETTINGS_FILE" > "$temp_file"

            mv "$temp_file" "$SETTINGS_FILE"
        else
            # Fallback to Python
            python3 - "$SETTINGS_FILE" "$mcp_config" <<'PYTHON'
import json
import sys

settings_file = sys.argv[1]
mcp_config = json.loads(sys.argv[2])

with open(settings_file, 'r') as f:
    settings = json.load(f)

if 'mcpServers' not in settings:
    settings['mcpServers'] = {}

settings['mcpServers']['matryoshka'] = mcp_config

with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
PYTHON
        fi
    else
        # Create new settings file
        cat > "$SETTINGS_FILE" <<EOF
{
  "mcpServers": {
    "matryoshka": $mcp_config
  }
}
EOF
    fi
}

remove_matryoshka_config() {
    if [ ! -f "$SETTINGS_FILE" ]; then
        print_warning "No settings file found"
        return 0
    fi

    if command -v jq &>/dev/null; then
        local temp_file
        temp_file=$(mktemp)

        jq 'del(.mcpServers.matryoshka)' "$SETTINGS_FILE" > "$temp_file"
        mv "$temp_file" "$SETTINGS_FILE"
    else
        python3 - "$SETTINGS_FILE" <<'PYTHON'
import json
import sys

settings_file = sys.argv[1]

with open(settings_file, 'r') as f:
    settings = json.load(f)

if 'mcpServers' in settings and 'matryoshka' in settings['mcpServers']:
    del settings['mcpServers']['matryoshka']

with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
PYTHON
    fi

    print_status "Removed Matryoshka MCP configuration"
}

check_status() {
    echo "Matryoshka MCP Status Check"
    echo "==========================="

    # Check package runner
    local runner
    if runner=$(detect_package_runner); then
        print_status "Package runner: $runner"
    else
        print_error "No package runner found (need bunx or npx)"
        return 1
    fi

    # Check Matryoshka
    local args=""
    [ "$runner" = "npx" ] && args="-y"

    if $runner $args matryoshka-rlm --version &>/dev/null 2>&1; then
        local version
        version=$($runner $args matryoshka-rlm --version 2>/dev/null || echo "unknown")
        print_status "Matryoshka installed: $version"
    else
        print_warning "Matryoshka not installed (will install on first use)"
    fi

    # Check settings
    if [ -f "$SETTINGS_FILE" ]; then
        if grep -q '"matryoshka"' "$SETTINGS_FILE" 2>/dev/null; then
            print_status "MCP configured in settings.local.json"
        else
            print_warning "MCP not configured in settings.local.json"
        fi
    else
        print_warning "settings.local.json not found"
    fi

    echo ""
    echo "Settings file: $SETTINGS_FILE"
}

main() {
    case "${1:-}" in
        --check)
            check_status
            exit 0
            ;;
        --uninstall)
            remove_matryoshka_config
            exit 0
            ;;
        --help|-h)
            echo "Usage: $0 [--check|--uninstall|--help]"
            echo ""
            echo "Options:"
            echo "  --check      Check current status without modifying"
            echo "  --uninstall  Remove Matryoshka MCP configuration"
            echo "  --help       Show this help message"
            exit 0
            ;;
    esac

    echo "Matryoshka MCP Setup"
    echo "===================="
    echo ""

    # Step 1: Detect package runner
    echo "Step 1: Detecting package runner..."
    local runner
    if ! runner=$(detect_package_runner); then
        print_error "Neither bun nor npm found. Install one first."
        echo ""
        echo "Install Bun:  curl -fsSL https://bun.sh/install | bash"
        echo "Install Node: https://nodejs.org/"
        exit 1
    fi
    print_status "Using $runner"

    # Step 2: Test Matryoshka
    echo ""
    echo "Step 2: Validating Matryoshka..."
    if test_matryoshka "$runner"; then
        print_status "Matryoshka is available"
    else
        print_warning "Matryoshka package will be installed on first use"
    fi

    # Step 3: Configure MCP
    echo ""
    echo "Step 3: Configuring MCP settings..."
    merge_settings "$runner"
    print_status "Updated $SETTINGS_FILE"

    # Step 4: Show result
    echo ""
    echo "Setup Complete!"
    echo "==============="
    echo ""
    echo "Matryoshka MCP is now configured for fando-plan."
    echo ""
    echo "When running /fando-plan on plans with 300+ lines:"
    echo "  - Plans will be loaded into Matryoshka once"
    echo "  - Domain-specific slices extracted per reviewer"
    echo "  - Estimated 75%+ token savings per iteration"
    echo ""
    echo "To verify: ./scripts/install.sh --check"
}

main "$@"
