#!/usr/bin/env bash
# AutoGrader — Database & Artifacts Reset Script (Bash)
set -e

echo "Clearing AutoGrader SQLite databases and artifacts..."

rm -f backend/data/autograder.db backend/data/test_autograder.db data/autograder.db data/test_autograder.db

rm -rf backend/data/artifacts/* backend/data/test-artifacts/* data/artifacts/* data/test-artifacts/* 2>/dev/null || true

echo "AutoGrader database and artifacts have been completely cleared!"
echo "When you run or restart the server, clean empty tables will be initialized automatically."

