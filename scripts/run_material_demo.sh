#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output_root="${1:-$project_root/sessions/material-demo}"
library_path="$output_root/library"

# Uses authored fixtures; Chinese image OCR needs documents extras and Tesseract.
python -m interview_forge library add "$project_root/examples/materials/redis-interview.png" \
  --kind interview --library "$library_path"
python -m interview_forge library add "$project_root/examples/materials/redis-answer.docx" \
  --kind answer --library "$library_path"
python -m interview_forge start \
  --resume "$project_root/examples/redis/resume.md" \
  --repo "$project_root/examples/redis/repo" \
  --jd "$project_root/examples/redis/jd.md" \
  --library "$library_path" \
  --session "$output_root/session" --max-turns 6 --run
