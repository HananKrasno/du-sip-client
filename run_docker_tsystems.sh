#!/bin/bash
if [ -z "$1" ]; then
  echo "Error: the SIP number is not specified"
  echo "Usage: run_docker_tsystems.sh <sipNumber"
  echo "   Example: run_docker_tsystems.sh echoTest"
  exit -1
fi
docker run -it --network host --privileged  --device /dev/snd:/dev/snd  du-sip-client:1.0.0 ./run_client.sh --profile tsystem --sip-number $1@localhost