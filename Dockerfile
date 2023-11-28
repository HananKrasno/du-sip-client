FROM python:3.9.16-slim-buster AS dependencies
FROM ubuntu:20.04 AS dependencies

RUN echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections
ENV TZ=Europe/UTC
RUN DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential \
    make \
    git \
    wget \
    curl \
    gcc \
    swig \
    vim \
    unzip \
    libssl-dev \
    --assume-yes \
    --no-install-recommends

FROM dependencies AS pjsip

WORKDIR /root

RUN wget https://github.com/pjsip/pjproject/archive/refs/heads/master.zip --no-check-certificate
RUN unzip master.zip

#RUN wget https://github.com/pjsip/pjproject/archive/refs/tags/2.13.1.tar.gz --no-check-certificate
#RUN tar xvf 2.13.1.tar.gz
WORKDIR /root/pjproject-master
RUN ./configure CFLAGS="-fPIC" --enable-shared --disable-video && \
    make dep && \
    make && \
    make install && \
    ldconfig

FROM pjsip AS pjsua2

RUN apt-get install -y python3-dev
WORKDIR /root/pjproject-master/pjsip-apps/src/swig/python

RUN make && \
    make install

FROM pjsua2 AS du_app
RUN apt-get update && apt-get install -y \
    python3.8-tk \
    alsa-base \
    alsa-utils
WORKDIR /root/du-sip-client
COPY sip_client.py .
COPY ducall.py .
COPY udpsniffer.py .
COPY run_client.sh .