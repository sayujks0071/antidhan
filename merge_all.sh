#!/bin/bash
set -e
ids=(30 28 27 26 23 22 21 20 12 10 9 8)
for id in "${ids[@]}"; do
  echo "Processing #$id..."
  gh pr checkout $id
  git fetch origin
  git merge origin/main --no-edit || {
     echo "Conflict detected in #$id. Resolving with --ours..."
     git diff --name-only --diff-filter=U | xargs git checkout --ours
     git add .
     git commit -m "Merge main (auto-resolve ours)"
  }
  git push
  gh pr ready $id || true
  gh pr merge $id --merge
done
