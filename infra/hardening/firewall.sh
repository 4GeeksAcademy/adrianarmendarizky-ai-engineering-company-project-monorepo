#!/usr/bin/env bash
# Firewall for a Brasaland server (IPv4). Everything coming in is dropped
# unless a rule below allows it. Run as root.
set -e
iptables -F INPUT
iptables -P INPUT DROP
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT    # SSH, for operations
iptables -A INPUT -p tcp --dport 443 -j ACCEPT   # HTTPS: API + dashboard (SSE/WebSocket also travel over HTTPS)
# Not opened on purpose: 6379 (Redis), 6333 (Qdrant), 5555 (Flower),
# the database, and the MCP admin port. They stay internal.
