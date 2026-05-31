#!/usr/bin/env bash
# Bulk-install every skill in this library into the user-wide Claude Code
# skills directory under a chosen prefix — typically "mikko-" so the slash
# commands group under `/mikko<Tab>`. Each skill is copied (not symlinked) so
# the frontmatter `name:` field can be rewritten to match the prefixed
# directory name without mutating the library's canonical sources.
#
# Usage:
#   ./install-mikko.sh                       # default prefix "mikko-"
#   ./install-mikko.sh --prefix bobs-        # use a different prefix
#   ./install-mikko.sh --dry-run             # show what would happen, do nothing
#
# Skills already starting with the prefix (e.g. `mikko-help`) are not
# double-prefixed. Existing installs at the target paths are replaced.
#
# Library skills stay unchanged. To install one skill at a time without the
# bulk-rename, use `install.sh <name>` (which keeps the source name and
# symlinks to the library copy).

set -euo pipefail

PREFIX="mikko-"
TARGET_DIR="${HOME}/.claude/skills"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            PREFIX="$2"
            shift 2
            ;;
        --target-dir)
            TARGET_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            sed -n 's/^# \{0,1\}//p' "$0" | head -n 18
            exit 0
            ;;
        *)
            echo "error: unknown argument '$1'" >&2
            exit 2
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="${SCRIPT_DIR}/skills"

if [[ ! -d "${SKILLS_ROOT}" ]]; then
    echo "error: no skills/ directory at ${SKILLS_ROOT}" >&2
    exit 1
fi

mkdir -p "${TARGET_DIR}"

count=0
for skill_dir in "${SKILLS_ROOT}"/*/; do
    src_name="$(basename "${skill_dir}")"
    if [[ ! -f "${skill_dir}SKILL.md" ]]; then
        continue
    fi

    # Don't double-prefix skills that already start with the prefix.
    if [[ "${src_name}" == "${PREFIX}"* ]]; then
        dest_name="${src_name}"
    else
        dest_name="${PREFIX}${src_name}"
    fi
    dest="${TARGET_DIR}/${dest_name}"

    if [[ ${DRY_RUN} -eq 1 ]]; then
        echo "would install: ${skill_dir%/} -> ${dest}"
        count=$((count + 1))
        continue
    fi

    if [[ -e "${dest}" ]] && [[ ! -L "${dest}" ]]; then
        echo "replacing: ${dest}"
        rm -rf "${dest}"
    elif [[ -L "${dest}" ]]; then
        echo "removing existing symlink: ${dest}"
        rm "${dest}"
    fi

    cp -R "${skill_dir%/}" "${dest}"

    # Rewrite frontmatter `name:` line so Claude Code's skill listing shows
    # the prefixed name. sed -i on macOS needs a backup suffix; we use
    # `-i.bak` and remove the backup afterward for cross-platform support.
    if [[ -f "${dest}/SKILL.md" ]]; then
        sed -i.bak "s|^name: ${src_name}\$|name: ${dest_name}|" "${dest}/SKILL.md"
        rm -f "${dest}/SKILL.md.bak"
    fi

    # Copy any skills/_lib/<name>.py files the skill imports as a sibling.
    # Each skill in the source repo imports shared lib modules from
    # ../_lib/<name>.py at dev time; after install (copy mode) the destination
    # is flat, so we copy on-demand based on what the skill's scripts import.
    if [[ -d "${SKILLS_ROOT}/_lib" ]]; then
        for lib_file in "${SKILLS_ROOT}/_lib"/*.py; do
            [[ -f "${lib_file}" ]] || continue
            lib_module="$(basename "${lib_file}" .py)"
            # Defensive: lib names get interpolated into a grep -E pattern.
            # Refuse anything that isn't a pure Python identifier so a future
            # name with regex metachars (`.`, `+`, etc.) can't silently miscopy.
            if [[ ! "${lib_module}" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
                echo "WARN: skipping _lib/${lib_module}.py - name is not a pure Python identifier" >&2
                continue
            fi
            # grep skill scripts for an import of the lib name. Anchored to
            # start-of-line (with optional leading whitespace) so commented
            # references like `# import skills_audit_lib was the old way` don't
            # cause spurious copies.
            if grep -qrE "^[[:space:]]*(import|from)[[:space:]]+${lib_module}\b" "${dest}" \
                --include="*.py" --include="*.mjs" --include="*.js" 2>/dev/null; then
                cp "${lib_file}" "${dest}/"
            fi
        done
    fi

    echo "installed: ${dest}"
    count=$((count + 1))
done

if [[ ${DRY_RUN} -eq 1 ]]; then
    echo "(dry run — ${count} skill(s) would be installed)"
else
    echo "${count} skill(s) installed under ${TARGET_DIR}/${PREFIX}*"
fi
