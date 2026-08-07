#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf '%s\n' \
        'Usage: link-gym-coach-skill.sh --link|--check' \
        '' \
        '  --link   Back up the installed SKILL.md and replace it with a repository symlink.' \
        '  --check  Verify that Hermes uses the repository SKILL.md.'
}

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_skill=$(realpath -- "${script_dir}/../skills/gym-coach/SKILL.md")
hermes_root=${HERMES_HOME:-"${HOME}/.hermes"}
target_dir="${hermes_root}/skills/health/gym-coach"
target_skill="${target_dir}/SKILL.md"

if [[ ! -f "${source_skill}" ]]; then
    printf 'Repository skill not found: %s\n' "${source_skill}" >&2
    exit 1
fi

is_current_link() {
    [[ -L "${target_skill}" ]] &&
        [[ "$(readlink -f -- "${target_skill}")" == "${source_skill}" ]]
}

case "${1:-}" in
    --check)
        if is_current_link; then
            printf 'Hermes skill is linked to %s\n' "${source_skill}"
            exit 0
        fi
        printf 'Hermes skill is not linked to the repository.\n' >&2
        exit 1
        ;;
    --link)
        if [[ -L "${target_dir}" ]]; then
            printf 'Refusing to install through a symlinked target directory: %s\n' \
                "${target_dir}" >&2
            exit 1
        fi
        mkdir -p -- "${target_dir}"
        if is_current_link; then
            printf 'Hermes skill is already linked to %s\n' "${source_skill}"
            exit 0
        fi
        if [[ -d "${target_skill}" ]]; then
            printf 'Refusing to replace a directory at %s\n' "${target_skill}" >&2
            exit 1
        fi
        if [[ -e "${target_skill}" || -L "${target_skill}" ]]; then
            backup_skill="${target_skill}.backup.$(date -u +%Y%m%dT%H%M%SZ)"
            mv -- "${target_skill}" "${backup_skill}"
            printf 'Previous skill backed up to %s\n' "${backup_skill}"
        fi
        ln -s -- "${source_skill}" "${target_skill}"
        printf 'Hermes skill linked to %s\n' "${source_skill}"
        printf 'Restart Hermes to reload it: hermes gateway restart\n'
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
