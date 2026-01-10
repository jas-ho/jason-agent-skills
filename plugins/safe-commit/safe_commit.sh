#!/bin/bash
# Safe Commit - Optimized for Python, Shell, and Markdown
# Validates and auto-fixes code before committing
#
# === ARCHITECTURE PATTERN ===
# This script follows a two-phase approach for all file types:
#
# 1. AUTOFIX PHASE (autofix_* functions):
#    - Run formatters and auto-fixers with --fix/--write flags
#    - Goal: Fix everything that can be automatically fixed
#    - Modified files are automatically re-staged
#    - Examples: ruff format, ruff check --fix, shfmt -w, markdownlint --fix
#
# 2. VALIDATION PHASE (validate_* functions):
#    - Run linters and type checkers, display output to agent
#    - Goal: Show agent what tools report, let them interpret
#    - Display raw tool output without parsing
#    - Examples: ruff check (without --fix), mypy, shellcheck, markdownlint (without --fix)
#
# The "user" is an intelligent LLM agent that can read tool output directly.
# We don't need to parse "All checks passed!" vs errors - just show the output.
#
# When adding support for new languages, follow this pattern:
# - autofix_<lang>(): Use ALL available auto-fixers with their fix flags
# - validate_<lang>(): Run validators and echo their output (no parsing)
#
# === TOOL PRIORITY PATTERN ===
# For Python tools (ruff, mypy), we prioritize project-managed tools:
#   1. Project dev environment (uv run --group dev) - sees dependencies, respects project config
#   2. UV-managed isolated tool (uv tool run) - consistent version, isolated
#   3. Global PATH - fallback to system installation
#
# For non-Python tools (shfmt, shellcheck, markdownlint, prettier), we use PATH only.
# For Python markdown tools (mdformat), we use project env → PATH.
#

set -euo pipefail

# Configuration
MAX_LINES=${MAX_LINES:-800}
WARN_LINES=${WARN_LINES:-300}
SENSITIVE_PATTERNS=${SENSITIVE_PATTERNS:-"\.env|credentials|secrets|\.pem$|\.key$|password|token"}
LOCAL_PATTERNS=${LOCAL_PATTERNS:-"\.local\.|\.local$|^local\."}

# Git root (set during preflight)
GIT_ROOT=""

# Colors for stderr output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}ℹ${NC} $*" >&2; }
log_warn() { echo -e "${YELLOW}⚠${NC} $*" >&2; }
log_error() { echo -e "${RED}✗${NC} $*" >&2; }
log_success() { echo -e "${GREEN}✓${NC} $*" >&2; }

# Tool detection - check if tools are actually usable
check_tools() {
    local missing=()

    # Python tools - check project env → uv tool → PATH (matching autofix/validate logic)
    for tool in ruff mypy; do
        local found=false

        # Try project dev environment first (only works with pyproject.toml)
        if [ -f "$GIT_ROOT/pyproject.toml" ] && command -v uv >/dev/null 2>&1; then
            if uv run --group dev "$tool" --version >/dev/null 2>&1; then
                found=true
            fi
        fi

        # Try uv tool run (isolated managed tool)
        if [ "$found" = false ] && command -v uv >/dev/null 2>&1; then
            if uv tool run "$tool" --version >/dev/null 2>&1; then
                found=true
            fi
        fi

        # Try global PATH
        if [ "$found" = false ] && command -v "$tool" >/dev/null 2>&1; then
            found=true
        fi

        if [ "$found" = false ]; then
            missing+=("$tool")
        fi
    done

    # Other tools - check PATH only
    for tool in shfmt shellcheck markdownlint prettier mdformat; do
        command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
    done

    if [ ${#missing[@]} -gt 0 ]; then
        echo "MISSING_TOOLS: ${missing[*]}"
        log_warn "Some tools are unavailable: ${missing[*]}"
    fi
}

# Pre-flight checks
preflight_checks() {
    log_info "Running pre-flight checks..."
    log_info "Git root: $GIT_ROOT"

    if git diff --cached --quiet; then
        log_error "No staged changes to commit"
        echo "ERROR: No staged changes to commit"
        exit 1
    fi

    local staged_files
    staged_files=$(git diff --cached --name-only --diff-filter=ACM)

    if [ -z "$staged_files" ]; then
        log_error "No staged files found"
        echo "ERROR: No staged files found"
        exit 1
    fi

    local num_files
    num_files=$(echo "$staged_files" | wc -l | tr -d ' ')
    log_success "Found $num_files staged file(s)"

    echo "$staged_files"
}

# Auto-fix Python file
autofix_python() {
    local file="$1"

    # Priority: project env → uv tool → global PATH
    # Note: pyproject.toml is required for uv run --group dev to work
    if [ -f "$GIT_ROOT/pyproject.toml" ] && command -v uv >/dev/null 2>&1; then
        # Use project dev environment (sees all deps, respects project config)
        uv run --group dev ruff format "$file" >/dev/null 2>&1 || true
        uv run --group dev ruff check --fix "$file" >/dev/null 2>&1 || true
    elif command -v uv >/dev/null 2>&1; then
        # Use uv-managed isolated tool
        uv tool run ruff format "$file" >/dev/null 2>&1 || true
        uv tool run ruff check --fix "$file" >/dev/null 2>&1 || true
    elif command -v ruff >/dev/null 2>&1; then
        # Fallback to global installation
        ruff format "$file" >/dev/null 2>&1 || true
        ruff check --fix "$file" >/dev/null 2>&1 || true
    fi

    # Check if file was modified and re-stage if so
    if ! git diff --quiet -- "$file" 2>/dev/null; then
        git add "$file"
        log_success "Auto-fixed and re-staged: $file"
        echo "AUTOFIXED: $file"
    fi
}

# Auto-fix Shell script
autofix_shell() {
    local file="$1"

    # Note: shellcheck has no auto-fix mode, only shfmt does
    # shfmt is not a Python tool, so PATH only
    if command -v shfmt >/dev/null 2>&1; then
        shfmt -w "$file" >/dev/null 2>&1 || true
    fi

    # Check if file was modified and re-stage if so
    if ! git diff --quiet -- "$file" 2>/dev/null; then
        git add "$file"
        log_success "Auto-fixed and re-staged: $file"
        echo "AUTOFIXED: $file"
    fi
}

# Auto-fix Markdown file
autofix_markdown() {
    local file="$1"

    # markdownlint (Node.js tool - PATH only)
    if command -v markdownlint >/dev/null 2>&1; then
        markdownlint --fix "$file" >/dev/null 2>&1 || true
    fi

    # prettier (Node.js tool - PATH only)
    if command -v prettier >/dev/null 2>&1; then
        prettier --write "$file" >/dev/null 2>&1 || true
    # mdformat (Python tool - try project env first, then PATH)
    elif [ -f "$GIT_ROOT/pyproject.toml" ] && command -v uv >/dev/null 2>&1; then
        uv run --group dev mdformat "$file" >/dev/null 2>&1 || true
    elif command -v mdformat >/dev/null 2>&1; then
        mdformat "$file" >/dev/null 2>&1 || true
    fi

    # Check if file was modified and re-stage if so
    if ! git diff --quiet -- "$file" 2>/dev/null; then
        git add "$file"
        log_success "Auto-fixed and re-staged: $file"
        echo "AUTOFIXED: $file"
    fi
}

# Validate Python file - just show tool output, let agent interpret
validate_python() {
    local file="$1"

    echo ""
    echo "=== Validating: $file ==="

    # Run ruff check and show output
    # Priority: project env → uv tool → global PATH
    if [ -f "$GIT_ROOT/pyproject.toml" ] && command -v uv >/dev/null 2>&1; then
        echo "--- ruff check (via project env) ---"
        uv run --group dev ruff check "$file" 2>&1 || true
        echo ""
    elif command -v uv >/dev/null 2>&1; then
        echo "--- ruff check (via uv tool) ---"
        uv tool run ruff check "$file" 2>&1 || true
        echo ""
    elif command -v ruff >/dev/null 2>&1; then
        echo "--- ruff check ---"
        ruff check "$file" 2>&1 || true
        echo ""
    else
        echo "--- ruff: not available ---"
        echo ""
    fi

    # Run mypy and show output
    # Priority: project env → uv tool → global PATH
    if [ -f "$GIT_ROOT/pyproject.toml" ] && command -v uv >/dev/null 2>&1; then
        echo "--- mypy (via project env) ---"
        uv run --group dev mypy "$file" 2>&1 || true
        echo ""
    elif command -v uv >/dev/null 2>&1; then
        echo "--- mypy (via uv tool) ---"
        uv tool run mypy "$file" 2>&1 || true
        echo ""
    elif command -v mypy >/dev/null 2>&1; then
        echo "--- mypy ---"
        mypy "$file" 2>&1 || true
        echo ""
    else
        echo "--- mypy: not available ---"
        echo ""
    fi
}

# Validate Shell script - just show tool output, let agent interpret
validate_shell() {
    local file="$1"

    echo ""
    echo "=== Validating: $file ==="

    # Run shellcheck and show output (not a Python tool - PATH only)
    if command -v shellcheck >/dev/null 2>&1; then
        echo "--- shellcheck ---"
        shellcheck "$file" 2>&1 || true
        echo ""
    else
        echo "--- shellcheck: not available ---"
        echo ""
    fi
}

# Validate Markdown file - just show tool output, let agent interpret
validate_markdown() {
    local file="$1"

    echo ""
    echo "=== Validating: $file ==="

    # Run markdownlint and show output (Node.js tool - PATH only)
    if command -v markdownlint >/dev/null 2>&1; then
        echo "--- markdownlint ---"
        markdownlint "$file" 2>&1 || true
        echo ""
    else
        echo "--- markdownlint: not available ---"
        echo ""
    fi
}

# Check for sensitive files
check_sensitive_files() {
    local files="$1"
    while IFS= read -r file; do
        if echo "$file" | grep -iE "$SENSITIVE_PATTERNS" >/dev/null; then
            echo "$file"
        fi
    done <<<"$files"
}

# Check for local files
check_local_files() {
    local files="$1"
    while IFS= read -r file; do
        if echo "$file" | grep -E "$LOCAL_PATTERNS" >/dev/null; then
            echo "$file"
        fi
    done <<<"$files"
}

# Analyze commit size
analyze_commit_size() {
    local stats
    stats=$(git diff --cached --shortstat)

    local insertions=0
    local deletions=0

    if echo "$stats" | grep -q "insertion"; then
        insertions=$(echo "$stats" | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+')
    fi

    if echo "$stats" | grep -q "deletion"; then
        deletions=$(echo "$stats" | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+')
    fi

    local total=$((insertions + deletions))

    log_info "Commit size: +$insertions -$deletions lines ($total total)"

    if [ "$total" -gt "$MAX_LINES" ]; then
        echo "SIZE_WARNING: Large commit ($total lines). Consider splitting into smaller commits."
    elif [ "$total" -gt "$WARN_LINES" ]; then
        echo "SIZE_INFO: Moderately large commit ($total lines)"
    fi

    echo "STATS: +$insertions -$deletions ($total total)"
}

# Generate test cases for testing the safe-commit script
generate_test_cases() {
    local test_dir=".safe-commit-tests"

    log_info "Generating test cases in $test_dir/"
    mkdir -p "$test_dir"

    # Clean Python file
    cat >"$test_dir/clean.py" <<'EOF'
"""Clean Python file with no errors."""


def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    print(greet("World"))
    print(f"2 + 3 = {add(2, 3)}")
EOF

    # Python with fixable issues (bad formatting, missing spaces)
    cat >"$test_dir/fixable.py" <<'EOF'
def add(a:int,b:int)->int:
    return a+b
x=add(1,2)
EOF

    # Python with lint error (undefined name)
    cat >"$test_dir/lint_error.py" <<'EOF'
"""File with lint error."""


def broken() -> None:
    """This function references an undefined variable."""
    print(undefined_variable)  # noqa: F821 - intentional error for testing
EOF

    # Python with type error
    cat >"$test_dir/type_error.py" <<'EOF'
"""File with type error."""


def needs_str(x: str) -> str:
    """Function that requires a string."""
    return x.upper()


# Type error: passing int to function expecting str
result: str = needs_str(123)  # type: ignore - intentional error for testing
EOF

    # Clean shell script
    cat >"$test_dir/clean.sh" <<'EOF'
#!/bin/bash
# Clean shell script with no errors

set -euo pipefail

main() {
    echo "Hello, World!"
}

main "$@"
EOF
    chmod +x "$test_dir/clean.sh"

    # Shell with shellcheck issue (unquoted variable)
    cat >"$test_dir/shell_issue.sh" <<'EOF'
#!/bin/bash
# Shell script with shellcheck warnings

echo $UNQUOTED_VAR
cd $SOME_PATH
EOF
    chmod +x "$test_dir/shell_issue.sh"

    # Clean markdown
    cat >"$test_dir/clean.md" <<'EOF'
# Test Document

This is a clean markdown file.

## Section

- Item 1
- Item 2
- Item 3
EOF

    # Markdown with formatting issues
    cat >"$test_dir/markdown_issue.md" <<'EOF'
#Bad Heading
No blank line before this paragraph.

Multiple blank lines below:



Too many!
EOF

    # Local file (should be blocked)
    cat >"$test_dir/config.local.py" <<'EOF'
"""Local config file - should be blocked."""
LOCAL_CONFIG = {"key": "value"}
EOF

    # Sensitive file (should warn)
    cat >"$test_dir/.env.example" <<'EOF'
# Example env file - should trigger sensitive file warning
SECRET_KEY=example_secret_key
API_TOKEN=example_token
EOF

    log_success "Test cases generated in $test_dir/"
    echo ""
    log_info "Test scenarios:"
    echo ""
    echo "1. Clean Python file (should pass):"
    echo "   git add $test_dir/clean.py && $0"
    echo ""
    echo "2. Python with fixable issues (should auto-fix):"
    echo "   git add $test_dir/fixable.py && $0"
    echo ""
    echo "3. Python with lint error (shows error in output):"
    echo "   git add $test_dir/lint_error.py && $0"
    echo ""
    echo "4. Python with type error (shows error in output):"
    echo "   git add $test_dir/type_error.py && $0"
    echo ""
    echo "5. Shell script (clean):"
    echo "   git add $test_dir/clean.sh && $0"
    echo ""
    echo "6. Shell with issues (shows shellcheck warnings):"
    echo "   git add $test_dir/shell_issue.sh && $0"
    echo ""
    echo "7. Local file (should block):"
    echo "   git add $test_dir/config.local.py && $0"
    echo ""
    echo "8. Sensitive file (should warn):"
    echo "   git add $test_dir/.env.example && $0"
    echo ""
    log_info "To cleanup: rm -rf $test_dir && git restore --staged $test_dir 2>/dev/null || true"
}

# Main execution
main() {
    # Handle --generate-tests flag
    if [ "${1:-}" = "--generate-tests" ]; then
        generate_test_cases
        exit 0
    fi
    log_info "=== Safe Commit Validation ==="

    # Detect git root first (before any subshells)
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        log_error "Not in a git repository"
        echo "ERROR: Not in a git repository"
        exit 1
    fi
    GIT_ROOT=$(git rev-parse --show-toplevel)

    # Tool detection
    check_tools

    # Pre-flight
    STAGED_FILES=$(preflight_checks)

    # Auto-fix files by type
    log_info "Auto-fixing staged files..."
    while IFS= read -r file; do
        # Use absolute path for file operations
        local abs_file="$GIT_ROOT/$file"
        if [ -f "$abs_file" ]; then
            case "$file" in
            *.py)
                autofix_python "$abs_file"
                ;;
            *.sh | *.bash)
                autofix_shell "$abs_file"
                ;;
            *.md | *.markdown)
                autofix_markdown "$abs_file"
                ;;
            esac
        fi
    done <<<"$STAGED_FILES"

    # Refresh staged files (may have changed after auto-fix)
    STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)

    # Validation by type - just show output, don't count errors
    log_info "Running validators..."
    while IFS= read -r file; do
        # Use absolute path for file operations
        local abs_file="$GIT_ROOT/$file"
        if [ -f "$abs_file" ]; then
            case "$file" in
            *.py)
                validate_python "$abs_file"
                ;;
            *.sh | *.bash)
                validate_shell "$abs_file"
                ;;
            *.md | *.markdown)
                validate_markdown "$abs_file"
                ;;
            esac
        fi
    done <<<"$STAGED_FILES"

    # Security/safety checks
    log_info "Running security and safety checks..."
    SENSITIVE=$(check_sensitive_files "$STAGED_FILES")
    LOCAL=$(check_local_files "$STAGED_FILES")

    # Commit size
    analyze_commit_size

    # Report
    echo ""
    echo "=== Summary ==="
    NUM_FILES=$(echo "$STAGED_FILES" | wc -l | tr -d ' ')
    echo "Files staged: $NUM_FILES"

    # Hard block on local files
    if [ -n "$LOCAL" ]; then
        echo ""
        echo "LOCAL FILES DETECTED (commit blocked):"
        echo "$LOCAL"
        log_error "Local files must not be committed - unstage them first"
        exit 1
    fi

    # Warn about sensitive files
    if [ -n "$SENSITIVE" ]; then
        echo ""
        echo "SENSITIVE FILES DETECTED:"
        echo "$SENSITIVE"
        log_warn "Review carefully - these may contain secrets"
    fi

    # Done - agent interprets validation output
    echo ""
    log_info "Validation complete - review output above"
    exit 0
}

main "$@"
