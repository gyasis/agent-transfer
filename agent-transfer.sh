#!/bin/bash

# Agent Transfer Script for Claude Code
# 
# STANDALONE SCRIPT - No Python package installation required!
# 
# Usage:
#   Export: ./agent-transfer.sh export [output-file] [--all]
#   Import: ./agent-transfer.sh import <input-file.tar.gz>
#
# IMPORTANT: This script works standalone for import operations.
#            No need to install the Python package - just use this script!
#
# Workflow:
#   Machine A (with agent-transfer installed):
#     agent-transfer export my-agents.tar.gz
#
#   Machine B (no installation needed):
#     ./agent-transfer.sh import my-agents.tar.gz
#     (Just copy this script and the .tar.gz file)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEFAULT_EXPORT_FILE="claude-agents-backup_${TIMESTAMP}.tar.gz"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Global conflict mode (default: interactive diff)
CONFLICT_MODE="diff"

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if colordiff is available
check_colordiff() {
    if command -v colordiff &> /dev/null; then
        return 0
    fi
    return 1
}

# Show unified diff between two files with colors
show_diff() {
    local existing="$1"
    local incoming="$2"
    local filename="$3"

    echo -e "\n${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}Diff: ${filename}${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

    if check_colordiff; then
        diff -u "$existing" "$incoming" | colordiff | head -100
    elif diff --color=auto /dev/null /dev/null &> /dev/null 2>&1; then
        diff --color=auto -u "$existing" "$incoming" | head -100
    else
        diff -u "$existing" "$incoming" | head -100
    fi

    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Show side-by-side comparison
show_side_by_side() {
    local existing="$1"
    local incoming="$2"
    local filename="$3"

    echo -e "\n${BOLD}${CYAN}Side-by-Side: ${filename}${NC}\n"

    if command -v sdiff &> /dev/null; then
        sdiff -w 120 "$existing" "$incoming" | head -50
    else
        echo -e "${RED}─── EXISTING ───${NC}"
        head -20 "$existing"
        echo -e "\n${GREEN}─── INCOMING ───${NC}"
        head -20 "$incoming"
    fi
}

# Get next available duplicate filename with numeric suffix
get_duplicate_name() {
    local dir="$1"
    local name="$2"
    local stem="${name%.*}"
    local ext="${name##*.}"
    local counter=1

    while [ -f "$dir/${stem}_${counter}.${ext}" ]; do
        counter=$((counter + 1))
    done

    echo "${stem}_${counter}.${ext}"
}

# Resolve a single file conflict interactively
resolve_conflict_interactive() {
    local existing="$1"
    local incoming="$2"
    local target_dir="$3"
    local filename=$(basename "$existing")

    echo -e "\n${BOLD}${YELLOW}┌──────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BOLD}${YELLOW}│  Conflict Detected: ${filename}${NC}"
    echo -e "${BOLD}${YELLOW}└──────────────────────────────────────────────────────────────┘${NC}"

    while true; do
        echo -e "\n${BOLD}Options:${NC}"
        echo -e "  ${CYAN}o${NC} - Overwrite with incoming"
        echo -e "  ${CYAN}k${NC} - Keep existing (skip)"
        echo -e "  ${CYAN}d${NC} - Duplicate (save as ${filename%.*}_1.${filename##*.})"
        echo -e "  ${CYAN}v${NC} - View unified diff"
        echo -e "  ${CYAN}s${NC} - View side-by-side"
        echo ""

        read -p "Choice [o/k/d/v/s]: " -n 1 -r choice
        echo

        case "$choice" in
            o|O)
                cp "$incoming" "$target_dir/$filename"
                print_success "Overwritten: $filename"
                return 0
                ;;
            k|K)
                echo -e "${DIM}Kept existing: $filename${NC}"
                return 1
                ;;
            d|D)
                local new_name=$(get_duplicate_name "$target_dir" "$filename")
                cp "$incoming" "$target_dir/$new_name"
                print_success "Saved as duplicate: $new_name"
                return 0
                ;;
            v|V)
                show_diff "$existing" "$incoming" "$filename"
                ;;
            s|S)
                show_side_by_side "$existing" "$incoming" "$filename"
                ;;
            *)
                print_warning "Invalid choice. Please enter o, k, d, v, or s."
                ;;
        esac
    done
}

# Resolve conflict based on mode
resolve_conflict() {
    local existing="$1"
    local incoming="$2"
    local target_dir="$3"
    local filename=$(basename "$existing")

    case "$CONFLICT_MODE" in
        overwrite)
            cp "$incoming" "$target_dir/$filename"
            print_success "Overwritten: $filename"
            return 0
            ;;
        keep)
            echo -e "${DIM}Kept existing: $filename${NC}"
            return 1
            ;;
        duplicate)
            local new_name=$(get_duplicate_name "$target_dir" "$filename")
            cp "$incoming" "$target_dir/$new_name"
            print_success "Saved as duplicate: $new_name"
            return 0
            ;;
        diff|*)
            resolve_conflict_interactive "$existing" "$incoming" "$target_dir"
            return $?
            ;;
    esac
}

# Function to check if Claude Code is installed
check_claude_code_installed() {
    if command -v claude &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to find Claude Code agents directories
find_agent_directories() {
    local dirs=()
    
    # Check user-level agents
    if [ -d "$HOME/.claude/agents" ]; then
        dirs+=("$HOME/.claude/agents:user")
    fi
    
    # Check project-level agents in current directory
    if [ -d ".claude/agents" ]; then
        dirs+=("$(pwd)/.claude/agents:project")
    fi
    
    # Check parent directories for project agents (up to 3 levels)
    local current_dir="$(pwd)"
    for i in {1..3}; do
        local check_dir="$(dirname "$current_dir")"
        if [ -d "$check_dir/.claude/agents" ]; then
            dirs+=("$check_dir/.claude/agents:project")
        fi
        current_dir="$check_dir"
    done
    
    printf '%s\n' "${dirs[@]}"
}

# Function to check if uv is available
check_uv() {
    if command -v uv &> /dev/null; then
        return 0
    fi
    return 1
}

# Function to check if Python selector is available
check_python_selector() {
    local selector_path="$SCRIPT_DIR/agent-selector.py"
    if [ ! -f "$selector_path" ]; then
        return 1
    fi
    
    # Prefer uv if available (isolated environment)
    if check_uv; then
        return 0
    fi
    
    # Fall back to python3 with rich check
    if command -v python3 &> /dev/null; then
        if python3 -c "import rich" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# Function to use Python selector for interactive agent selection
select_agents_interactive() {
    local selector_path="$SCRIPT_DIR/agent-selector.py"
    local requirements_path="$SCRIPT_DIR/requirements.txt"
    local selected_files=()
    
    print_info "Launching interactive agent selector..."
    
    # Use uv if available (isolated environment, no pollution)
    if check_uv; then
        print_info "Using uv for isolated execution (dependencies won't affect your environment)"
        # Run with uv - automatically handles dependencies in isolated env
        # uv will read requirements.txt and install dependencies automatically
        local uv_cmd
        if [ -f "$requirements_path" ]; then
            # Use requirements.txt if available
            uv_cmd="cd '$SCRIPT_DIR' && uv run --with rich --with pyyaml python3 '$selector_path'"
        else
            # Fallback to inline dependencies
            uv_cmd="cd '$SCRIPT_DIR' && uv run --with rich --with pyyaml python3 '$selector_path'"
        fi
        while IFS= read -r line; do
            if [ -n "$line" ] && [ -f "$line" ]; then
                selected_files+=("$line")
            fi
        done < <(eval "$uv_cmd" 2>&1)
    elif [ -f "$requirements_path" ] && command -v python3 &> /dev/null; then
        # Fall back to python3 with requirements check
        if ! python3 -c "import rich, yaml" 2>/dev/null; then
            print_warning "Rich library not found. Install with: pip install -r $requirements_path"
            print_info "Or install uv for automatic dependency management: curl -LsSf https://astral.sh/uv/install.sh | sh"
            return 1
        fi
        while IFS= read -r line; do
            if [ -n "$line" ] && [ -f "$line" ]; then
                selected_files+=("$line")
            fi
        done < <(python3 "$selector_path" 2>&1)
    else
        print_error "Python 3 not found. Please install Python 3 or uv."
        return 1
    fi
    
    if [ ${#selected_files[@]} -eq 0 ]; then
        return 1
    fi
    
    printf '%s\n' "${selected_files[@]}"
    return 0
}

# Export function: Collect and zip agents
export_agents() {
    local output_file="${1:-$DEFAULT_EXPORT_FILE}"
    local use_interactive="${2:-true}"
    local temp_dir=$(mktemp -d)
    local found_any=false
    local selected_agents=()
    
    print_info "Starting agent export..."
    
    # Try interactive selection if requested and available
    if [ "$use_interactive" != "false" ] && check_python_selector; then
        print_info "Interactive selection available. Use --all to export all agents."
        read -p "Use interactive selection? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            print_info "Launching interactive agent selector..."
            selected_agents=($(select_agents_interactive))
            
            if [ ${#selected_agents[@]} -eq 0 ]; then
                print_warning "No agents selected. Exiting."
                rm -rf "$temp_dir"
                exit 0
            fi
            
            print_success "Selected ${#selected_agents[@]} agent(s) for export"
            
            # Copy selected agents to temp directory
            for agent_file in "${selected_agents[@]}"; do
                if [ -f "$agent_file" ]; then
                    found_any=true
                    local agent_name=$(basename "$agent_file")
                    
                    # Determine if user or project level
                    if [[ "$agent_file" == "$HOME/.claude/agents"* ]]; then
                        mkdir -p "$temp_dir/user-agents"
                        cp "$agent_file" "$temp_dir/user-agents/$agent_name"
                    else
                        mkdir -p "$temp_dir/project-agents"
                        # Try to preserve relative path
                        local rel_path=$(realpath --relative-to="$(pwd)" "$(dirname "$agent_file")" 2>/dev/null || echo ".claude/agents")
                        mkdir -p "$temp_dir/project-agents/$rel_path"
                        cp "$agent_file" "$temp_dir/project-agents/$rel_path/$agent_name"
                    fi
                fi
            done
        fi
    fi
    
    # Fall back to exporting all agents if interactive wasn't used or failed
    if [ "$found_any" == false ]; then
        print_info "Exporting all agents..."
        
        # Find all agent directories
        local agent_dirs=($(find_agent_directories))
        
        if [ ${#agent_dirs[@]} -eq 0 ]; then
            print_error "No agent directories found!"
            print_info "Checked locations:"
            print_info "  - User-level: $HOME/.claude/agents"
            print_info "  - Project-level: .claude/agents (current and parent directories)"
            rm -rf "$temp_dir"
            exit 1
        fi
        
        # Copy agents to temp directory
        for dir_info in "${agent_dirs[@]}"; do
            IFS=':' read -r dir_path dir_type <<< "$dir_info"
            
            if [ -d "$dir_path" ] && [ "$(ls -A "$dir_path" 2>/dev/null)" ]; then
                found_any=true
                local agent_count=$(find "$dir_path" -name "*.md" -type f | wc -l)
                
                if [ "$dir_type" == "user" ]; then
                    print_info "Found $agent_count user-level agent(s) in $dir_path"
                    mkdir -p "$temp_dir/user-agents"
                    cp -r "$dir_path"/*.md "$temp_dir/user-agents/" 2>/dev/null || true
                else
                    print_info "Found $agent_count project-level agent(s) in $dir_path"
                    mkdir -p "$temp_dir/project-agents"
                    # Preserve relative path structure
                    local rel_path=$(realpath --relative-to="$(pwd)" "$dir_path" 2>/dev/null || echo "$dir_path")
                    mkdir -p "$temp_dir/project-agents/$(dirname "$rel_path")"
                    cp -r "$dir_path"/*.md "$temp_dir/project-agents/$rel_path/" 2>/dev/null || true
                fi
            fi
        done
    fi
    
    if [ "$found_any" == false ]; then
        print_error "No agent files found in any directory!"
        rm -rf "$temp_dir"
        exit 1
    fi
    
    # Create metadata file
    cat > "$temp_dir/metadata.txt" <<EOF
Claude Code Agents Backup
Created: $(date)
Export Version: 1.0
System: $(uname -s)
User: $(whoami)
Home Directory: $HOME
EOF
    
    # Create the archive
    print_info "Creating archive: $output_file"
    tar -czf "$output_file" -C "$temp_dir" .
    
    # Cleanup
    rm -rf "$temp_dir"
    
    # Get file size
    local file_size=$(du -h "$output_file" | cut -f1)
    
    print_success "Export complete!"
    print_info "Archive: $output_file ($file_size)"
    print_info "Location: $(pwd)/$output_file"
    
    # List what was exported
    print_info "Contents:"
    tar -tzf "$output_file" | sed 's/^/  - /'
}

# Import function: Detect Claude Code and unzip agents
import_agents() {
    local input_file="${1}"

    if [ -z "$input_file" ]; then
        print_error "Please provide an input file"
        echo "Usage: $0 import <backup-file.tar.gz> [--overwrite|--keep|--duplicate]"
        exit 1
    fi

    if [ ! -f "$input_file" ]; then
        print_error "File not found: $input_file"
        exit 1
    fi

    print_info "Starting agent import..."
    print_info "Input file: $input_file"
    print_info "Conflict mode: $CONFLICT_MODE"
    print_info "Standalone mode - no Python package required!"
    
    # Check if Claude Code is installed
    if ! check_claude_code_installed; then
        print_warning "Claude Code CLI not found in PATH"
        print_info "Attempting to detect Claude Code installation..."
        
        # Check common installation locations
        local claude_paths=(
            "$HOME/.local/bin/claude"
            "/usr/local/bin/claude"
            "/usr/bin/claude"
            "$(which claude 2>/dev/null || true)"
        )
        
        local found_claude=false
        for path in "${claude_paths[@]}"; do
            if [ -f "$path" ] && [ -x "$path" ]; then
                print_info "Found Claude Code at: $path"
                found_claude=true
                break
            fi
        done
        
        if [ "$found_claude" == false ]; then
            print_error "Claude Code not found!"
            print_info "Please install Claude Code first:"
            print_info "  npm install -g @anthropic-ai/claude-code"
            print_warning "Continuing anyway - agents will be extracted but may not be usable"
        fi
    else
        print_success "Claude Code detected: $(which claude)"
    fi
    
    # Extract to temp directory first
    local temp_dir=$(mktemp -d)
    print_info "Extracting archive..."
    tar -xzf "$input_file" -C "$temp_dir"
    
    # Read metadata if available
    if [ -f "$temp_dir/metadata.txt" ]; then
        print_info "Backup metadata:"
        cat "$temp_dir/metadata.txt" | sed 's/^/  /'
    fi
    
    # Import user-level agents
    local imported_count=0
    local skipped_count=0
    local conflict_count=0

    if [ -d "$temp_dir/user-agents" ] && [ "$(ls -A "$temp_dir/user-agents" 2>/dev/null)" ]; then
        local agent_count=$(find "$temp_dir/user-agents" -name "*.md" -type f | wc -l)
        print_info "Found $agent_count user-level agent(s) to import"

        mkdir -p "$HOME/.claude/agents"

        # Process each agent file individually for proper conflict handling
        for agent_file in "$temp_dir/user-agents"/*.md; do
            if [ -f "$agent_file" ]; then
                local agent_name=$(basename "$agent_file")
                local target_file="$HOME/.claude/agents/$agent_name"

                if [ -f "$target_file" ]; then
                    conflict_count=$((conflict_count + 1))
                    # Use conflict resolver
                    if resolve_conflict "$target_file" "$agent_file" "$HOME/.claude/agents"; then
                        imported_count=$((imported_count + 1))
                    else
                        skipped_count=$((skipped_count + 1))
                    fi
                else
                    # No conflict - just copy
                    cp "$agent_file" "$target_file"
                    print_success "Imported: $agent_name"
                    imported_count=$((imported_count + 1))
                fi
            fi
        done

        print_success "User-level agents directory: $HOME/.claude/agents"
    fi
    
    # Import project-level agents
    if [ -d "$temp_dir/project-agents" ] && [ "$(ls -A "$temp_dir/project-agents" 2>/dev/null)" ]; then
        local agent_count=$(find "$temp_dir/project-agents" -name "*.md" -type f | wc -l)
        print_info "Found $agent_count project-level agent(s) to import"

        # Find or create .claude/agents directory
        local project_agents_dir=".claude/agents"

        # Check if we're in a project directory
        if [ ! -d ".claude" ]; then
            print_warning "No .claude directory found in current location"
            read -p "Create .claude/agents here? (Y/n): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                mkdir -p "$project_agents_dir"
                print_info "Created $project_agents_dir"
            else
                print_info "Skipping project-level agents import"
                skipped_count=$((skipped_count + agent_count))
            fi
        else
            mkdir -p "$project_agents_dir"
        fi

        # Copy agents with conflict handling
        if [ -d "$project_agents_dir" ]; then
            find "$temp_dir/project-agents" -name "*.md" -type f | while read -r agent_file; do
                local agent_name=$(basename "$agent_file")
                local target_file="$project_agents_dir/$agent_name"

                if [ -f "$target_file" ]; then
                    conflict_count=$((conflict_count + 1))
                    # Use conflict resolver
                    if resolve_conflict "$target_file" "$agent_file" "$project_agents_dir"; then
                        imported_count=$((imported_count + 1))
                    else
                        skipped_count=$((skipped_count + 1))
                    fi
                else
                    # No conflict - just copy
                    cp "$agent_file" "$target_file"
                    print_success "Imported: $agent_name"
                    imported_count=$((imported_count + 1))
                fi
            done

            print_success "Project-level agents imported to: $(pwd)/$project_agents_dir"
        fi
    fi
    
    # Cleanup
    rm -rf "$temp_dir"

    # Summary
    echo ""
    echo -e "${BOLD}${GREEN}┌──────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BOLD}${GREEN}│                    Import Complete!                          │${NC}"
    echo -e "${BOLD}${GREEN}├──────────────────────────────────────────────────────────────┤${NC}"
    echo -e "${BOLD}${GREEN}│${NC}  Imported:  ${GREEN}$imported_count${NC}"
    echo -e "${BOLD}${GREEN}│${NC}  Conflicts: ${YELLOW}$conflict_count${NC}"
    echo -e "${BOLD}${GREEN}│${NC}  Skipped:   ${DIM}$skipped_count${NC}"
    echo -e "${BOLD}${GREEN}└──────────────────────────────────────────────────────────────┘${NC}"

    # Verify import
    print_info "Verifying imported agents..."
    local total_available=0

    if [ -d "$HOME/.claude/agents" ]; then
        local user_count=$(find "$HOME/.claude/agents" -name "*.md" -type f | wc -l)
        total_available=$((total_available + user_count))
        if [ $user_count -gt 0 ]; then
            print_info "  User-level: $user_count agent(s)"
        fi
    fi

    if [ -d ".claude/agents" ]; then
        local project_count=$(find ".claude/agents" -name "*.md" -type f | wc -l)
        total_available=$((total_available + project_count))
        if [ $project_count -gt 0 ]; then
            print_info "  Project-level: $project_count agent(s)"
        fi
    fi

    print_success "Total agents available: $total_available"

    # Test Claude Code if available
    if check_claude_code_installed; then
        print_info "To verify agents, run: claude"
        print_info "Then use: /agents list"
    fi
}

# Parse conflict mode from arguments
parse_conflict_mode() {
    for arg in "$@"; do
        case "$arg" in
            --overwrite)
                CONFLICT_MODE="overwrite"
                ;;
            --keep)
                CONFLICT_MODE="keep"
                ;;
            --duplicate)
                CONFLICT_MODE="duplicate"
                ;;
            --diff)
                CONFLICT_MODE="diff"
                ;;
        esac
    done
}

# Main script logic
case "${1:-}" in
    export)
        # Check for --all flag
        if [ "${2:-}" == "--all" ]; then
            export_agents "${3:-}" "false"
        else
            export_agents "${2:-}" "true"
        fi
        ;;
    import)
        # Parse conflict mode flags
        parse_conflict_mode "$@"
        # Get input file (skip flags)
        input_file=""
        for arg in "${@:2}"; do
            case "$arg" in
                --overwrite|--keep|--duplicate|--diff)
                    # Skip flags
                    ;;
                *)
                    input_file="$arg"
                    break
                    ;;
            esac
        done
        import_agents "$input_file"
        ;;
    install-deps)
        print_info "Installing dependencies for interactive selection..."
        if check_uv; then
            print_info "Using uv (recommended - isolated environment)"
            print_info "uv will automatically handle dependencies when running the script"
            print_success "No manual installation needed with uv!"
            print_info "Dependencies will be installed automatically in isolated environment on first run"
        elif command -v pip3 &> /dev/null; then
            print_warning "Installing to your Python environment (consider using uv for isolation)"
            pip3 install -r "$SCRIPT_DIR/requirements.txt"
            print_success "Dependencies installed!"
        elif command -v pip &> /dev/null; then
            print_warning "Installing to your Python environment (consider using uv for isolation)"
            pip install -r "$SCRIPT_DIR/requirements.txt"
            print_success "Dependencies installed!"
        else
            print_error "pip not found."
            print_info "Recommended: Install uv for isolated execution:"
            print_info "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            exit 1
        fi
        ;;
    *)
        echo "Claude Code Agent Transfer Script (Standalone)"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "STANDALONE SCRIPT - No Python package installation required for import!"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "Usage:"
        echo "  $0 export [output-file.tar.gz] [--all]           - Export agents"
        echo "  $0 import <input-file.tar.gz> [conflict-option]  - Import agents"
        echo ""
        echo "Examples:"
        echo ""
        echo "  # On Machine A (with agent-transfer installed):"
        echo "  agent-transfer export my-agents.tar.gz"
        echo ""
        echo "  # On Machine B (NO INSTALLATION NEEDED - just use this script!):"
        echo "  ./agent-transfer.sh import my-agents.tar.gz"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "IMPORTANT: Import works completely standalone!"
        echo "  - Just copy this script and the .tar.gz file"
        echo "  - No Python package installation required"
        echo "  - No dependencies needed for import"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "Export Options:"
        echo "  $0 export                                    # Interactive selection (if Python available)"
        echo "  $0 export --all                              # Export all agents (no Python needed)"
        echo "  $0 export my-agents-backup.tar.gz            # Custom filename"
        echo "  $0 export my-agents-backup.tar.gz --all      # All agents with custom filename"
        echo ""
        echo "Import Options:"
        echo "  $0 import backup.tar.gz                      # Default: interactive diff/merge"
        echo "  $0 import backup.tar.gz --overwrite          # Overwrite all existing files"
        echo "  $0 import backup.tar.gz --keep               # Keep existing, skip conflicts"
        echo "  $0 import backup.tar.gz --duplicate          # Save as agent_1.md, agent_2.md, etc."
        echo "  $0 import backup.tar.gz --diff               # Interactive diff (default)"
        echo ""
        echo "Conflict Handling (during import):"
        echo "  --diff      Interactive mode (default):"
        echo "              - View unified diff between files"
        echo "              - View side-by-side comparison"
        echo "              - Choose: overwrite, keep, or duplicate per file"
        echo "  --overwrite Replace all existing files with incoming"
        echo "  --keep      Skip all conflicts, keep existing files"
        echo "  --duplicate Save incoming as filename_1.md, filename_2.md, etc."
        echo ""
        echo "Features:"
        echo "  ✅ Import: Works standalone - no Python/dependencies needed"
        echo "  ✅ Export: Works standalone with --all flag (no Python needed)"
        echo "  ✅ Interactive export: Optional (requires Python/uv for beautiful UI)"
        echo "  ✅ Automatically finds user-level and project-level agents"
        echo "  ✅ Detects Claude Code installation on import"
        echo "  ✅ Smart conflict resolution with diff viewing"
        echo "  ✅ Uses colordiff for enhanced display (if available)"
        echo "  ✅ Preserves agent metadata"
        echo ""
        echo "For Interactive Export (Optional):"
        echo "  - Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "  - Or run: $0 install-deps"
        echo ""
        echo "For Enhanced Diff Display (Optional):"
        echo "  - Install colordiff: sudo apt install colordiff  # Debian/Ubuntu"
        echo "                       brew install colordiff     # macOS"
        exit 1
        ;;
esac

