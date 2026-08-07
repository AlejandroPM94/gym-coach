#!/usr/bin/env bash
set -euo pipefail

cd /home/alexpm/code/gym-coach

# Hermes can start with WSL before Docker Desktop has restored the Compose
# project. Keep the five-minute poll quiet during that short bootstrap window;
# the next scheduled run will retry once PostgreSQL is accepting connections.
if ! (exec 3<>/dev/tcp/127.0.0.1/5432) 2>/dev/null; then
    exit 0
fi
exec 3>&-
exec 3<&-

exec uv run gym-coach automation poll-hevy
