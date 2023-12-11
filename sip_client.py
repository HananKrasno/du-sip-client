import pjsua2 as pj
import time
import socket
from array import array
import argparse
import sys
import os
import logging
from logging import handlers

import settings
import ducall
import log
import endpoint as ep


MOBOTIX = "mobotix"
TS = "ts"
CUSTOM = "custom"

# write=sys.stdout.write
write = logging.info

parser = argparse.ArgumentParser()

parser.add_argument("--profile", choices=[MOBOTIX, TS, CUSTOM], default=MOBOTIX)
parser.add_argument("--sip-number", default="")
parser.add_argument("--user", default="")
parser.add_argument("--sip-uri", default="")
parser.add_argument("--password", default="")
parser.add_argument("--registrar-uri", default="")
parser.add_argument("--proxy", default="")
parser.add_argument("--recording-file", default=None)
parser.add_argument("--downport", type=int, default=6600, help="UDP port for PCM stream from Streamer to SIP server")
parser.add_argument("--upport", type=int, default=6700, help="UDP port for PCM stream from SIP server to Streamer")
parser.add_argument("--use-sniffer", action="store_true", help="When defined the downstream socket will work in sniffing mode. "
                                                               "It allows to read the data when the port is used by another application")
parser.add_argument("--sample-rate", type=int, default=16000)
parser.add_argument("--frame-length-msec", type=int, default=40)



args = parser.parse_args()


# Create a custom account class to handle account events
class MyAccount(pj.Account):
    def __init__(self):
        pj.Account.__init__(self)

    def onRegState(self, prm):
        if prm.code == 200:
            write("Registration successful")


class SipCall:
    def __init__(self, profile):
        self.custom_audio_media = None
        self.logger = log.Logger()
        self.profile = profile
        self.sipNumber = None
        self.upStreamPort = 0
        self.downStreamPort = 0

    def initAppConfig(self):
        USE_THREADS = False
        self.appConfig = settings.AppConfig()
        if USE_THREADS:
            self.appConfig.epConfig.uaConfig.threadCnt = 1
            self.appConfig.epConfig.uaConfig.mainThreadOnly = False
        else:
            self.appConfig.epConfig.uaConfig.threadCnt = 0
            self.appConfig.epConfig.uaConfig.mainThreadOnly = True
        self.appConfig.epConfig.logConfig.writer = self.logger
        self.appConfig.epConfig.logConfig.filename = "/tmp/du-sip/sip_cpp.log"
        self.appConfig.epConfig.logConfig.fileFlags = pj.PJ_O_APPEND
        self.appConfig.epConfig.logConfig.level = 5
        self.appConfig.epConfig.logConfig.consoleLevel = 5
        self.appConfig.epConfig.uaConfig.userAgent = "pygui-" + self.ep.libVersion().full
        return self.appConfig

    def initLib(self):
        # Create a pjsua2 Endpoint
        self.epStat = ep.Endpoint()
        self.ep = ep.Endpoint.instance

        # Initialize the endpoint
        self.ep.libCreate()
        # Initialize the endpoint library
        self.initAppConfig()
        self.ep.libInit(self.appConfig.epConfig)

    def listDevices(self):
        audio_dev_man = self.ep.audDevManager()

        # Print the list of audio input (capture) devices
        for i in range(0, audio_dev_man.getDevCount()):
            devInfo = audio_dev_man.getDevInfo(i)
            write(f"#{i}) {devInfo.name} inp: {devInfo.inputCount} out: {devInfo.outputCount}")

    def setSipNumber(self, defaultSipNumber):
        if args.sip_number == "":
            self.sipNumber = defaultSipNumber
        else:
            self.sipNumber = "sip:" + args.sip_number
        assert args.sip_number != "", f"SIP number is not defined"
        write(f"Sip number is: {self.sipNumber}")

    def createAccount(self, idUri, user, password, registrarUri, proxy):
        self.acfg = pj.AccountConfig()
        self.acfg.idUri = "sip:" + idUri
        self.acfg.regConfig.registrarUri = "sip:" + registrarUri
        if len(user) > 0:
            cred = pj.AuthCredInfo("digest", "*", user, 0, password)
            self.acfg.sipConfig.authCreds.append(cred)
        if len(proxy) > 0:
            self.acfg.sipConfig.proxies.append("sip:" + proxy)
        # Create the account
        self.acc = pj.Account()
        self.acc.create(self.acfg)
        try:
            self.acc.setRegistration(True)
        except pj.Error as error:
            write("Exception:" + error.info())
        except Exception as error:
            write("Exception:" + error.info())

        # self.acc.setRegistration(True)
        write("Account successfully created")

    def createTsAccount(self):
        self.createAccount("teleopertor@localhost", "teleopertor", args.password,
                       "cfc-top.germanywestcentral.cloudapp.azure.com",
                           "cfc-top.germanywestcentral.cloudapp.azure.com")


    def createMobotixAccount(self):
        self.acfg = pj.AccountConfig()
        self.acfg.idUri = "sip:driveu@10.20.97.100"
        cred = pj.AuthCredInfo("digest", "*", "driveu", 0, "")
        self.acfg.sipConfig.authCreds.append(cred)
        # Create the account
        self.acc = pj.Account()
        self.acc.cfg = self.acfg
        self.acc.create(self.acfg)

    def createCustomAccount(self):
        self.createAccount(args.sip_uri, args.user, args.password, args.registrar_uri, args.proxy)


    def start(self):
        self.initLib()
        # Create UDP transport
        self.transport_cfg = pj.TransportConfig()
        self.transport_cfg.port = 5060  # Change this port as needed
        transport = self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, callTest.appConfig.udp.config)
        # transport.create(transport_cfg)

        self.ep.libStart()
        if self.profile == TS:
            self.createTsAccount()
            self.setSipNumber(defaultSipNumber="sip:echoTest@localhost")
        elif self.profile == MOBOTIX:
            self.createMobotixAccount()
            self.setSipNumber(defaultSipNumber="sip:100@10.20.97.222")
        elif self.profile == CUSTOM:
            self.createCustomAccount()
            self.setSipNumber(defaultSipNumber="")

       # self.listDevices()
        self.downStreamPort = args.downport
        self.upStreamPort = args.upport
        write(f"Set SIP {self.profile} profile:  "
              f"\n\tnumber {self.sipNumber}"
              f"\n\tdown stream port {self.downStreamPort}"
              f"\n\tup stream port {self.upStreamPort}")

        audio_dev_man = self.ep.audDevManager()
        audio_dev_man.setNullDev()

    def call(self):
        self.start()
        # Make an outgoing call
        try:
            callUri = self.sipNumber
            self.myCall = ducall.Call(acc=self.acc, peer_uri=callUri, upStreamPort=self.upStreamPort,
                                      downStreamPort=self.downStreamPort, useSniffer=args.use_sniffer,
                                      playbackFile=args.recording_file, sampleRate=args.sample_rate, frameLen=args.frame_length_msec)
            self.call_param = pj.CallOpParam()
            self.call_param.opt.audioCount = 1
            self.call_param.opt.videoCount = 0
            self.myCall.makeCall(callUri, self.call_param)
            # Time for async procedures before running event loop
            time.sleep(1)
        except pj.Error as e:
            write("Error making the call:", str(e))

        # Run events loop
        while True:
            # Checks for events once per 10 Ms
            time.sleep(0.01)
            self.ep.libHandleEvents(10)

    def end(self):
        self.ep.libDestroy()


# This method is for testing and debugging purposes only. FileName has to be a full path to the
# recorded PCM stream like: "/home/me/work/pjproject/pjsip-apps/src/pygui/playfile"
def sendTestFile(fileName, frameLengthMS=40):
    audioData = array('B')
    with open(fileName, "rb") as f:
        audioData.fromfile(f, 96000)
    shift = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    frameLength = frameLengthMS * 0.001
    while True:
        barr = bytes(audioData[shift:shift + 640])
        sock.sendto(barr, ("0.0.0.0", 6700))
        shift += 640
        if shift >= 96000:
            shift = 0
        time.sleep(frameLength)

def initLogger(logPath):
    os.makedirs("/tmp/du-sip", mode=0o666, exist_ok=True)
 
    log = logging.getLogger('')
    log.setLevel(logging.DEBUG)
    format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(format)
    log.addHandler(ch)

    fh = handlers.RotatingFileHandler(logPath, maxBytes=(1048576 * 20), backupCount=7)
    fh.setFormatter(format)
    log.addHandler(fh)

# Run the main loop
try:
    # sendTestFile()
    initLogger("/tmp/du-sip/sip_py.log")
    # logging.basicConfig(filename="/tmp/du-sip/py.log", level=logging.DEBUG, format='%(asctime)s %(message)s')
    callTest = SipCall(args.profile)
    callTest.call()
except KeyboardInterrupt:
    write("Exiting...")

# Clean up
callTest.end()

