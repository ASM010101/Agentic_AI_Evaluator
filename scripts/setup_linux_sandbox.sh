#!/usr/bin/env bash
set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
  printf '%s\n' "This setup helper currently supports Debian/Ubuntu apt-based Linux." >&2
  exit 1
fi

APT=""
if [ "$(id -u)" -ne 0 ]; then
  if ! command -v sudo >/dev/null 2>&1; then
    printf '%s\n' "sudo is required when this script is not run as root." >&2
    exit 1
  fi
  APT="sudo"
fi

$APT apt-get update
$APT apt-get install -y bubblewrap gcc cppcheck flawfinder clang-tidy

printf '\nLinux AutoGrader toolchain:\n'
command -v bwrap
command -v gcc
command -v cppcheck
command -v flawfinder
command -v clang-tidy
printf '%s\n' "Bubblewrap sandbox tools are installed. Configure AUTOGRADER_RUNNER=bubblewrap."
