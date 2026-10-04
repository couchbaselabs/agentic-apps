#!/usr/bin/env bash
# Installs the jev JavaScript library into Couchbase and allowlists the TypeSafe endpoint.
#
#   export TYPESAFE_API_KEY=...        # your TypeSafe API key
#   export CB_PASSWORD=...             # Couchbase admin password
#   ./install.sh
#
# Optional: CB_HOST (default localhost), CB_USER (default Administrator)
set -euo pipefail

: "${TYPESAFE_API_KEY:?Set TYPESAFE_API_KEY to your TypeSafe API key}"
: "${CB_PASSWORD:?Set CB_PASSWORD to your Couchbase admin password}"
CB_HOST="${CB_HOST:-localhost}"
CB_USER="${CB_USER:-Administrator}"
LIB="jev_lib"

cd "$(dirname "$0")"
mkdir -p build

# Inject the key into a build copy (build/ is git-ignored); the source keeps the placeholder.
KEY="$TYPESAFE_API_KEY" perl -pe 's/"---"/"$ENV{KEY}"/g' "src/${LIB}.js" > "build/${LIB}.js"
if grep -q '"---"' "build/${LIB}.js"; then
  echo "Placeholder was not replaced; aborting." >&2
  exit 1
fi

echo "Installing JavaScript library '${LIB}' via the Query service (port 8093)..."
curl -sS -u "${CB_USER}:${CB_PASSWORD}" -X POST \
  "http://${CB_HOST}:8093/evaluator/v1/libraries/${LIB}" \
  --data-binary "@build/${LIB}.js"
echo

# CURL() is blocked by default. The allowlist is a cluster-level query setting, which
# is served by the cluster manager (port 8091). You can also set it in the web console:
# Settings > Query Settings > CURL() Allowlist.
echo "Allowlisting https://api.typesafe.ai for CURL()..."
curl -sS -u "${CB_USER}:${CB_PASSWORD}" -X POST \
  "http://${CB_HOST}:8091/settings/querySettings/curlAllowlist" \
  -d '{"all_access": false, "allowed_urls": ["https://api.typesafe.ai"]}'
echo

echo "Done. Next: run sql/01_register_functions.sql (with no query context set)."
