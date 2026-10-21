#!/usr/bin/env bash
# Starts the Brasaland app inside a GitHub Codespace with login working.
set -e
cd "$(dirname "$0")/.."

if [ -z "$CODESPACE_NAME" ] || [ -z "$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN" ]; then
  echo "This script is for GitHub Codespaces only."; exit 1
fi
if [ ! -f .env ]; then echo "No .env file found in $(pwd)"; exit 1; fi

D="$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN"
API="https://${CODESPACE_NAME}-8000.${D}"
WEBSITE="https://${CODESPACE_NAME}-3000.${D}"
BACKOFFICE="https://${CODESPACE_NAME}-3001.${D}"

cp .env "$HOME/.env.backup"
if [ -n "$(tail -c1 .env)" ]; then echo >> .env; fi

set_var() {
  if grep -q "^$1=" .env; then
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    echo "$1=$2" >> .env
  fi
}

set_var NEXT_PUBLIC_API_URL "$API"
set_var NEXT_PUBLIC_TELEMETRY_ENDPOINT "$API/telemetry/events"
set_var NEXT_PUBLIC_ALLOWED_RETURN_ORIGINS "$WEBSITE,$BACKOFFICE"
set_var FRONTEND_URL "$BACKOFFICE"

gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" >/dev/null 2>&1 || true

echo "Starting Redis and Qdrant..."
docker compose up -d --no-build redis qdrant
echo "Starting the API..."
docker compose up -d --no-build --no-deps --force-recreate api

echo "Waiting for the API to answer..."
for i in $(seq 1 60); do
  if curl -sf -o /dev/null http://localhost:8000/docs; then break; fi
  sleep 2
done

echo "Starting worker and flower..."
docker compose up -d --no-build --no-deps worker flower
echo "Restarting the web apps with fresh settings..."
docker compose rm -sfv ui
docker compose up -d --no-build --no-deps ui

code=$(curl -s -o /dev/null -w '%{http_code}' -X OPTIONS "$API/auth/login" \
  -H "Origin: $BACKOFFICE" -H "Access-Control-Request-Method: POST" || true)
echo
echo "Public API check: $code (200 means login can work)"
if [ "$code" != "200" ]; then
  echo "Set port 8000 to Public in the Ports tab, then run this script again."
fi
echo "Website:    $WEBSITE"
echo "Backoffice: $BACKOFFICE/login"
echo "(First page load takes a minute while Next.js compiles.)"
