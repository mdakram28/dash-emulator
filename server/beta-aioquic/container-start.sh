#!/bin/bash

set -e

# Listen for SIGINT signal and kill process on receiving signal
trap "exit" SIGINT SIGTERM

export DOLLAR='$'
envsubst </etc/nginx/common/nginx.template.conf >/etc/nginx/nginx.conf
cat /etc/nginx/nginx.conf

function tc_stats() {
  while true; do
    sleep 0.1
    echo "#EVENT" "TC_STAT" $(date +%s%3N) \
      $(tc -s -d class show dev eth0 | tr '\n' ' ') \
      $(tc -s -d qdisc show dev eth0 | tr '\n' ' ')
  done >>/run/event_logs_tc.txt
}

function tcpdump_collect() {
  tcpdump -i eth0 -s 65535 -w - >/run/server_out.pcap &
  tcpdump -i eth0 -s 65535 -w - >/run/server_in.pcap &
}

iptables -A OUTPUT -o eth0 -j NFLOG --nflog-group 1
iptables -A INPUT -i eth0 -j NFLOG --nflog-group 2

tc_stats &
tcpdump_collect &

PROTOCOL=$(cat "/run/config.json" | jq -r '.protocol')
LOG_LEVEL=$(cat "/run/config.json" | jq -r '.serverLogLevel')

echo "Detected LOG_LEVEL: $LOG_LEVEL"
echo "Detected PROTOCOL: $PROTOCOL"

if [[ "$PROTOCOL" == "tcp" ]]; then

  nginx -g "daemon off;"

elif [[ "$PROTOCOL" == "quic" ]]; then
  extra_args=()

  if [[ "$LOG_LEVEL" == "debug" ]]; then
    extra_args+=("--quic-log")
    extra_args+=("/run/server_log")
  fi

  python3 /src/aioquic/server.py -v \
    --port 443 \
    -c /opt/nginx/certs/localhost.crt \
    -k /opt/nginx/certs/localhost.key \
    "${extra_args[@]}"

else
  echo "Invalid protocol: $PROTOCOL"
fi
