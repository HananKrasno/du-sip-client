#!/bin/bash
while true; do
  echo "===============================  Starting sip client with the following parameters $@  ==============================="
  PYTHONPATH=:/root/pjproject-master/pjsip-apps/src/pygui python3 ./sip_client.py $@
  sleep 1
done