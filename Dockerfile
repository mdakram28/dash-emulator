FROM python:3.10

WORKDIR /src

# Download and install docker client
RUN apt-get update && \
    apt-get -y install apt-transport-https \
         ca-certificates \
         curl \
         gnupg2 \
         software-properties-common && \
    curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg > /tmp/dkey; apt-key add /tmp/dkey && \
    add-apt-repository \
       "deb [arch=amd64] https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") \
       $(lsb_release -cs) \
       stable" && \
    apt-get update && \
    apt-get -y install docker-ce knot-dnsutils net-tools

COPY requirements.txt /src
RUN pip install -r requirements.txt

COPY experiments-common experiments-common
RUN cd experiments-common && pip install .

COPY dash-emulator dash-emulator
RUN cd dash-emulator && pip install .

COPY dash_emulator_quic dash_emulator_quic
COPY scripts scripts
COPY setup.py .

RUN pip install .

ENTRYPOINT ["python", "/src/scripts/dash-emulator.py"]
