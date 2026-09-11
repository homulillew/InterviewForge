#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output_root="${1:-$project_root/sessions/demo}"
for scenario in redis rag service; do
  python -m interview_forge start \
    --resume "$project_root/examples/$scenario/resume.md" \
    --repo "$project_root/examples/$scenario/repo" \
    --jd "$project_root/examples/$scenario/jd.md" \
    --session "$output_root/$scenario" --max-turns 6 --run
done
