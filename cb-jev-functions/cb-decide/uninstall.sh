#!/usr/bin/env bash
# Removes the cb_decide JavaScript library. Run sql/99_cleanup.sql first to drop the functions.
set -euo pipefail
: "${CB_PASSWORD:?Set CB_PASSWORD to your Couchbase admin password}"
CB_HOST="${CB_HOST:-localhost}"
CB_USER="${CB_USER:-Administrator}"
curl -sS -u "${CB_USER}:${CB_PASSWORD}" -X DELETE \
  "http://${CB_HOST}:8093/evaluator/v1/libraries/decide_lib"
echo
