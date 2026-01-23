#!/usr/bin/env bash
set -euo pipefail
EXPECTED="${EXPECTED_EGRESS_IP:-}"
[[ -z "$EXPECTED" ]] && { echo "EXPECTED_EGRESS_IP not set"; exit 1; }
CURR="$(curl -s --max-time 2 https://api.ipify.org || true)"
[[ -z "$CURR" ]] && { echo "unable to resolve egress ip"; exit 2; }
if [[ "$CURR" != "$EXPECTED" ]]; then
  echo "FAIL: egress ip mismatch (curr=$CURR expected=$EXPECTED)"; exit 3
fi
echo "OK: $CURR"


