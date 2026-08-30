#!/bin/sh
set -e

# Two things this has to do that `npm run dev` in each app's own
# package.json doesn't handle correctly inside a container:
#
# 1. Port assignment. backoffice/package.json hardcodes
#    `next dev --port 3000` (correct for its LOCAL, non-Docker dev
#    workflow). Editing that script would change local dev too, so
#    instead this calls `next dev` directly, bypassing the npm script
#    entirely, to give backoffice port 3001 here without touching it.
#
# 2. Host binding. `next dev` defaults to binding 127.0.0.1, which is
#    unreachable from the host machine through Docker's port mapping --
#    --hostname 0.0.0.0 is required for the exposed ports to actually
#    work.

cleanup() {
  kill -TERM "$website_pid" "$backoffice_pid" 2>/dev/null
}
trap cleanup TERM INT

(cd website && npx next dev --port 3000 --hostname 0.0.0.0) &
website_pid=$!

(cd backoffice && npx next dev --port 3001 --hostname 0.0.0.0) &
backoffice_pid=$!

wait "$website_pid" "$backoffice_pid"
