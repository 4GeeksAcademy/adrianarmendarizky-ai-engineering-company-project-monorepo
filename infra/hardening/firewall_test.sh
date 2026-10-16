#!/usr/bin/env bash
# Live firewall test: a "client" container probes a "server" container
# before and after firewall.sh is applied. Uses Docker's default network.
# Needs Docker.
docker rm -f fw-server >/dev/null 2>&1
docker run -d --name fw-server --cap-add NET_ADMIN brasaland-ssh-demo \
  bash -c 'for p in 22 443 6379 6333 5555; do nc -lk $p >/dev/null & done; sleep 600' >/dev/null
sleep 2
IP=$(docker inspect -f '{{.NetworkSettings.Networks.bridge.IPAddress}}' fw-server)
echo "server ip: $IP"
probe() {
  for p in 22 443 6379 6333 5555; do
    if docker run --rm brasaland-ssh-demo nc -z -w 2 "$IP" $p; then
      echo "port $p: OPEN"
    else
      echo "port $p: BLOCKED"
    fi
  done
}
echo "== BEFORE firewall =="; probe
docker exec fw-server bash /usr/local/bin/firewall.sh && echo "(firewall applied)"
echo "== AFTER firewall =="; probe
docker rm -f fw-server >/dev/null
