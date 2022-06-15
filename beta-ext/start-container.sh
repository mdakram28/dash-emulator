#!/bin/bash

docker container run --name research-1 \
    -v /Users/akram/ucalgary/research/beta-emulator-quic/dataset:/usr/share/nginx/html:ro \
    -v /Users/akram/ucalgary/research:/research:ro \
    -p 55000:80 \
    --cap-add=NET_ADMIN \
    -P -d research:latest