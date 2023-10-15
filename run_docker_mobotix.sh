#!/bin/bash
docker run -it --network host --privileged  --device /dev/snd:/dev/snd  du-sip-client:1.0.0 ./run_client.sh --profile mobotix --sip-number 100@10.20.97.222