#!/usr/bin/env bash
# Checks an sshd_config file against the hardening rules.
# Usage: bash infra/hardening/check_ssh_config.sh /path/to/sshd_config
# A setting that is missing counts as FAIL, so the rule must be written down.
cfg="${1:-/etc/ssh/sshd_config}"
fail=0

check() {
  val=$(grep -Ei "^[[:space:]]*$1[[:space:]]" "$cfg" | tail -1 | awk '{print $2}')
  if [ "${val,,}" = "$2" ]; then
    echo "PASS  $1 = $val"
  else
    echo "FAIL  $1 = ${val:-(not set)}  (want $2)"
    fail=1
  fi
}

check PermitRootLogin no
check PasswordAuthentication no
check PubkeyAuthentication yes
check X11Forwarding no
check MaxAuthTries 3

if grep -Eiq "^[[:space:]]*AllowUsers[[:space:]]+[^[:space:]]" "$cfg"; then
  echo "PASS  AllowUsers is set"
else
  echo "FAIL  AllowUsers is not set (want a named list of users)"
  fail=1
fi
exit $fail
