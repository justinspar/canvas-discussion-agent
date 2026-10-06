#!/usr/bin/env bash
# Trigger one live Canvas agent cycle via GitHub Actions (no interactive prompt).
# Used by an external cron service (e.g. cron-job.org) or for a manual smoke test.
#
# Requires env:
#   GITHUB_TRIGGER_TOKEN  — classic PAT with `repo` + `workflow` (private repo)
# Optional:
#   GITHUB_REPOSITORY     — default justinspar/canvas-discussion-agent
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-justinspar/canvas-discussion-agent}"
TOKEN="${GITHUB_TRIGGER_TOKEN:?Set GITHUB_TRIGGER_TOKEN to a GitHub PAT with repo+workflow}"

curl -sS -f -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  "https://api.github.com/repos/${REPO}/dispatches" \
  -d '{"event_type":"canvas-agent-cycle","client_payload":{"source":"external-cron"}}'

echo "Triggered repository_dispatch canvas-agent-cycle on ${REPO}"
