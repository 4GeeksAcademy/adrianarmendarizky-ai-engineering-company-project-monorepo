FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-server iptables iproute2 netcat-openbsd \
 && rm -rf /var/lib/apt/lists/*

# A dedicated non-root user for day-to-day work. It has no password,
# so it can only log in with an SSH key. Root's password is locked.
RUN useradd --create-home --shell /bin/bash deploy \
 && passwd -l root \
 && mkdir -p /run/sshd /srv/brasaland/app /var/log/brasaland /etc/brasaland

# Separate folders with explicit permissions:
#   code   /srv/brasaland/app   deploy only
#   logs   /var/log/brasaland   deploy only
#   config /etc/brasaland       root owns it, deploy can read but not change it
RUN chown deploy:deploy /srv/brasaland/app /var/log/brasaland \
 && chmod 750 /srv/brasaland/app /var/log/brasaland \
 && chown root:deploy /etc/brasaland \
 && chmod 750 /etc/brasaland \
 && printf 'EXAMPLE_SETTING=not-a-real-secret\n' > /etc/brasaland/api.env \
 && chown root:deploy /etc/brasaland/api.env \
 && chmod 640 /etc/brasaland/api.env

COPY sshd_config.hardened /etc/ssh/sshd_config
COPY check_ssh_config.sh /usr/local/bin/check_ssh_config.sh
COPY firewall.sh /usr/local/bin/firewall.sh

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D", "-e"]
