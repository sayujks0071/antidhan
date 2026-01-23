#!/usr/bin/env bash
# jq-less Day-2 scorer JSON reader: prints compact PASS/FAIL line and exits 0/1

# Usage:
#   bash scripts/read_day2_pass.sh                # compact output
#   HEARTBEAT_MAX=5 FLAP_MAX=2 bash scripts/read_day2_pass.sh
#   QUIET=1 bash scripts/read_day2_pass.sh        # prints only PASS/FAIL

# Exit codes: 0=PASS, 1=FAIL, 2=JSON missing

set -euo pipefail
IFS=$'\n\t'
export TZ="${TZ:-Asia/Kolkata}"

HEARTBEAT_MAX="${HEARTBEAT_MAX:-5}"
FLAP_MAX="${FLAP_MAX:-2}"
FLATTEN_MS_MAX="${FLATTEN_MS_MAX:-2000}"
FRESH_WINDOW_SECS="${FRESH_WINDOW_SECS:-129600}" # 36h default
DIR="${DIR:-reports/burnin}"
QUIET="${QUIET:-0}"

have_jq() { command -v jq >/dev/null 2>&1; }

now_epoch() { date +%s; }

file_mtime_epoch() {
  local f="$1"
  if stat -f %m "$f" >/dev/null 2>&1; then
    stat -f %m "$f"       # macOS/BSD
  else
    stat -c %Y "$f"       # GNU
  fi
}

latest_day2_json() {
  ls -t "${DIR}/day2_"*.json 2>/dev/null | head -n1 || true
}

json_get_key_fallback() {
  # Not a general JSON parser; works for our scorer outputs
  local f="$1" k="$2"
  awk -v key="\"${k}\"" '
    BEGIN{FS=":"}
    $0 ~ key {
      sub(/.*:[[:space:]]*/, "", $0)
      gsub(/[[:space:]]*,?[[:space:]]*$/, "", $0)
      gsub(/[[:space:]]*[,}][[:space:]]*$/, "", $0)
      gsub(/^"[[:space:]]*/,"",$0); gsub(/[[:space:]]*"$/,"",$0)
      print $0; exit
    }' "$f"
}

read_vals() {
  local f="$1"
  if have_jq; then
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
    for key in status leader hb_marketdata hb_order_stream hb_scan leader_changes duplicates orphans flatten_ms config_sha git_head; do
      val="$(json_get_key_fallback "$f" "$key" | tr -d '\r')"
      echo "${key}=${val}"
    done
  fi
}

main() {
  local f; f="$(latest_day2_json)"
  if [[ -z "${f:-}" || ! -f "$f" ]]; then
    [[ "$QUIET" = "1" ]] || echo "DAY2 FAIL: JSON not found (${DIR}/day2_*.json)"
    exit 2
  fi

  local mt now age
  mt="$(file_mtime_epoch "$f")" || mt="0"
  now="$(now_epoch)"
  age=$(( now - mt ))

  # Load fields into assoc array
  declare -A kv=()
  while IFS='=' read -r k v; do
    [[ -n "${k:-}" ]] && kv["$k"]="${v:-}"
  done < <(read_vals "$f")

  # Coerce
  local status="${kv[status]:-}"
  local leader="${kv[leader]:-}"
  local hb_m="${kv[hb_marketdata]:-9999}"
  local hb_o="${kv[hb_order_stream]:-9999}"
  local hb_s="${kv[hb_scan]:-9999}"
  local flaps="${kv[leader_changes]:-9999}"
  local dups="${kv[duplicates]:-9999}"
  local orph="${kv[orphans]:-9999}"
  local flat_ms="${kv[flatten_ms]:-999999}"
  local sha="${kv[config_sha]:-}"
  local head="${kv[git_head]:-}"

  # Validate (fail closed)
  local reason=""
  if (( age > FRESH_WINDOW_SECS )); then reason="stale(${age}s)"; fi
  if [[ -z "$reason" && "$status" != "PASS" ]]; then reason="status=${status}"; fi
  if [[ -z "$reason" && "$leader" != "1" ]]; then reason="leader=${leader}"; fi

  if [[ -z "$reason" ]]; then
    awk -v m="${hb_m}" -v o="${hb_o}" -v s="${hb_s}" -v mx="${HEARTBEAT_MAX}" '
      BEGIN{ if (m>=mx || o>=mx || s>=mx) exit 1; else exit 0 }' \
    || reason="heartbeats>=${HEARTBEAT_MAX}s"
  fi
  if [[ -z "$reason" ]]; then
    awk -v fl="${flaps}" 'BEGIN{ exit (fl<=2 ? 0 : 1) }' || reason="leader_changes=${flaps}"
  fi
  if [[ -z "$reason" ]]; then
    awk -v d="${dups}" 'BEGIN{ exit (d==0 ? 0 : 1) }' || reason="duplicates=${dups}"
  fi
  if [[ -z "$reason" ]]; then
    awk -v r="${orph}" 'BEGIN{ exit (r==0 ? 0 : 1) }' || reason="orphans=${orph}"
  fi
  if [[ -z "$reason" ]]; then
    awk -v fm="${flat_ms}" -v mx="${FLATTEN_MS_MAX}" 'BEGIN{ exit (fm<=mx ? 0 : 1) }' \
    || reason="flatten_ms=${flat_ms}>${FLATTEN_MS_MAX}"
  fi

  if [[ -z "$reason" ]]; then
    if [[ "$QUIET" = "1" ]]; then
      echo "PASS"
    else
      printf "DAY2 PASS file=%s age=%ss leader=%s hb=%.3g/%.3g/%.3g flaps=%s dup=%s orph=%s flatten=%sms sha=%s head=%.8s\n" \
        "$f" "$age" "$leader" "$hb_m" "$hb_o" "$hb_s" "$flaps" "$dups" "$orph" "$flat_ms" "$sha" "$head"
    fi
    exit 0
  else
    if [[ "$QUIET" = "1" ]]; then
      echo "FAIL"
    else
      printf "DAY2 FAIL %s file=%s age=%ss leader=%s hb=%.3g/%.3g/%.3g flaps=%s dup=%s orph=%s flatten=%sms\n" \
        "$reason" "$f" "$age" "$leader" "$hb_m" "$hb_o" "$hb_s" "$flaps" "$dups" "$orph" "$flat_ms"
    fi
    exit 1
  fi
}

main "$@"


