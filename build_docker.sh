#!/bin/bash
tag="du-sip-client:1.0.0"
if [ ! -z "$1" ]; then
  tag="du-sip-client:$1"
fi
echo "Building docker image with the tag: $tag"
docker build --network=host -t $tag .

