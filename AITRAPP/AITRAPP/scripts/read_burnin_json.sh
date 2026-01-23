#!/usr/bin/env bash
# Reusable helper to read latest burnin JSON (jq-less fallback)
# Usage: source this file or call functions directly
set -euo pipefail
IFS=$'\n\t'

TZ="${TZ:-Asia/Kolkata}"
export TZ
FRESH_WINDOW_SECS=$((36*3600))   # 36h

now_epoch() {
  date +%s
}

# Cross-platform file mtime -> epoch (GNU/BSD stat)
file_mtime_epoch() {
  local f="$1"
  if stat -f %m "$f" >/dev/null 2>&1; then
    stat -f %m "$f"
  else
    stat -c %Y "$f"
  fi
}

latest_day2_json() {
  # Choose newest Day-2 JSON by mtime; quiet if none
  ls -t reports/burnin/day2_*.json 2>/dev/null | head -n1 || true
}

latest_day1_json() {
  # Choose newest Day-1 JSON by mtime; quiet if none
  ls -t reports/burnin/day1_*.json 2>/dev/null | head -n1 || true
}

have_jq() { command -v jq >/dev/null 2>&1; }

# Lenient JSON key extractor (numbers/strings) for our own scorer format
json_get_key_fallback() {
  # Usage: json_get_key_fallback <file> <key>
  # Returns raw value (unquoted for numbers, unquoted string if present).
  local f="$1" k="$2"
  # try number first
  awk -v key="\"${k}\"" '
    BEGIN{FS=":"}
    $0 ~ key {
      # join the rest of the line after first colon
      sub(/.*:[[:space:]]*/, "", $0);
      # strip trailing commas/braces/spaces
      gsub(/[[:space:]]*,?[[:space:]]*$/, "", $0);
      gsub(/[[:space:]]*[,}][[:space:]]*$/, "", $0);
      # strip quotes if any
      gsub(/^"[[:space:]]*/,"",$0); gsub(/[[:space:]]*"$/,"",$0);
      print $0; exit
    }
  ' "$f"
}

read_day2_json_values() {
  # Echo k=v lines for required fields; empty if missing
  local f="$1"
  if have_jq; then
    # Try jq fast path
    jq -r '
      [
        "status=" + ( .status // "" ),
        "leader=" + ( (.leader|tostring) // "" ),
        "hb_marketdata=" + ( (.heartbeats.market|tostring) // "" ),
        "hb_order_stream=" + ( (.heartbeats.orders|tostring) // "" ),
        "hb_scan=" + ( (.heartbeats.scan|tostring) // "" ),
        "leader_changes=" + ( (.leader_changes|tostring) // "" ),
        "duplicates=" + ( (.duplicates|tostring) // "" ),
        "orphans=" + ( (.orphans|tostring) // "" ),
        "flatten_ms=" + ( (.flatten_ms|tostring) // "" ),
        "config_sha=" + ( .config_sha // "" ),
        "git_head=" + ( .git_head // "" )
      ] | .[]
    ' "$f" 2>/dev/null || true
  else
    # Fallback parser (robust enough for our generated JSON)
    for key in status leader hb_marketdata hb_order_stream hb_scan leader_changes duplicates orphans flatten_ms config_sha git_head; do
      val="$(json_get_key_fallback "$f" "$key" | tr -d '\r')"
      echo "${key}=${val}"
    done
  fi
}

# Main entry point: read latest Day-2 JSON and print key=value pairs
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # Script is being executed directly
  DAY="${1:-day2}"
  if [[ "$DAY" == "day2" ]]; then
    f="$(latest_day2_json)"
  elif [[ "$DAY" == "day1" ]]; then
    f="$(latest_day1_json)"
  else
    echo "Usage: $0 [day1|day2]" >&2
    exit 1
  fi
  
  if [[ -z "${f:-}" || ! -f "$f" ]]; then
    echo "No ${DAY} JSON found" >&2
    exit 1
  fi
  
  read_day2_json_values "$f"
fi


