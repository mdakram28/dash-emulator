FROM nginx:1.21.1

RUN apt-get update && \
    apt install -y iproute2 procps tcpdump iptables

RUN apt install -y python3.4 python3-pip libssl-dev python3-dev build-essential libffi-dev

COPY aioquic /src/aioquic
RUN cd /src/aioquic && \
    pip3 install --upgrade pip && \
    pip3 install -r requirements.txt && \
    pip3 install -e .

RUN apt install -y jq socat dnsutils

COPY certs               /opt/nginx/certs
COPY nginx.template.conf    /etc/nginx/common/nginx.template.conf
COPY container-start.sh     /etc/nginx/common/container-start.sh
CMD ["bash", "/etc/nginx/common/container-start.sh"]
