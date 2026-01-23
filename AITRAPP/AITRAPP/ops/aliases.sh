# AITRAPP Safety Aliases
# Add to your ~/.zshrc or ~/.bashrc:
# source /path/to/AITRAPP/ops/aliases.sh

alias killnow='curl -s -X POST localhost:8000/flatten -H "Content-Type: application/json" -d "{\"reason\":\"manual\"}" | jq'
alias pause='curl -s -X POST localhost:8000/pause | jq'
alias resume='curl -s -X POST localhost:8000/resume | jq'
alias live='curl -s -X POST localhost:8000/mode -H "Content-Type: application/json" -d "{\"mode\":\"LIVE\",\"confirm\":\"CONFIRM LIVE TRADING\"}" | jq'
alias paper='curl -s -X POST localhost:8000/mode -H "Content-Type: application/json" -d "{\"mode\":\"PAPER\"}" | jq'
alias abort='pause && killnow && paper'
alias state='curl -s localhost:8000/state | jq'
alias risk='curl -s localhost:8000/risk | jq'
alias positions='curl -s localhost:8000/positions | jq'
alias metrics='curl -s localhost:8000/metrics | grep trader_'
alias health='curl -s localhost:8000/health | jq'

