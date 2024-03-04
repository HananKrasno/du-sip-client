#!/bin/bash
if [ -z "$TS_PASSWORD" ]; then
    echo "Error: TS_PASSWORD environment variable is not defined."
    echo "Please use the following sytax to define it: export TS_PASSWORD=<password>"
    exit -1
fi
if [ -z "$1" ]; then
  echo "Error: the SIP number is not specified"
  echo "Usage: run_docker_ts.sh <sipNumber"
  echo "   Example: run_docker_ts.sh echoTest"
  exit -1
fi
docker run -it --network host --privileged  --device /dev/snd:/dev/snd  du-sip-client:1.0.0 ./run_client.sh --profile ts --sip-number $1@localhost --password $TS_PASSWORD
