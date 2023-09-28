import pjsua2 as pj
import time
import socket
from array import array
import argparse

import settings
import ducall
import log
import endpoint as ep


MOBOTIX = "mobotix"
TSYSTEM = "tsystem"

parser = argparse.ArgumentParser()

parser.add_argument("--mode", choices=[MOBOTIX, TSYSTEM], default=MOBOTIX)
parser.add_argument("--calluri", default="")
parser.add_argument("--downport", type=int, default=6600)
parser.add_argument("--upport", type=int, default=6700)
parser.add_argument("--interval-in-ms", type=int)

args = parser.parse_args()


# Create a custom account class to handle account events
class MyAccount(pj.Account):
    def __init__(self):
        pj.Account.__init__(self)

    def onRegState(self, prm):
        if prm.code == 200:
            print("Registration successful")


class CallTest:
    def __init__(self, destination):
        self.custom_audio_media = None
        self.logger = log.Logger()
        self.destination = destination
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
        self.appConfig.epConfig.logConfig.filename = "driveu.log"
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
        audio_dev_info = self.ep.audDevManager.enumDev()

        # Print the list of audio input (capture) devices
        print("Audio Input (Capture) Devices:")
        for i, dev in enumerate(audio_dev_info):
            if dev.inputCount > 0:
                print(f"{i + 1}. {dev.name}")

        # Print the list of audio output (playback) devices
        print("\nAudio Output (Playback) Devices:")
        for i, dev in enumerate(audio_dev_info):
            if dev.outputCount > 0:
                print(f"{i + 1}. {dev.name}")

    def createMobotixAccount(self):
        self.acfg = pj.AccountConfig()
        self.acfg.idUri = "sip:hanan@10.20.97.100"
        # acfg.regConfig.registrarUri = "sip:sip.pjsip.org"
        cred = pj.AuthCredInfo("digest", "*", "hanan", 0, "")
        self.acfg.sipConfig.authCreds.append(cred)
        # Create the account
        self.acc = pj.Account()
        self.acc.create(self.acfg)

    def createTsystemAccount(self):
        self.acfg = pj.AccountConfig()
        self.acfg.idUri = "sip:teleopertor@localhost"
        self.acfg.regConfig.registrarUri = "sip:cfc-top.germanywestcentral.cloudapp.azure.com"
        cred = pj.AuthCredInfo("digest", "*", "teleopertor", 0, "D1sp4CFC#2022")
        self.acfg.sipConfig.authCreds.append(cred)
        self.acfg.sipConfig.proxies.append("sip:cfc-top.germanywestcentral.cloudapp.azure.com")
        # Create the account
        self.acc = pj.Account()
        self.acc.create(self.acfg)
        time.sleep(2)
        # self.acc.setRegistration(True)
        print("Account successfully created")


    def start(self):
        self.initLib()
        # Create UDP transport
        self.transport_cfg = pj.TransportConfig()
        self.transport_cfg.port = 5060  # Change this port as needed
        transport = self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, callTest.appConfig.udp.config)
        # transport.create(transport_cfg)

        self.ep.libStart()
        if self.destination == TSYSTEM:
            self.createTsystemAccount()
            self.sipNumber = "sip:100@localhost"
            self.downStreamPort = args.downport
            # self.upStreamPort = args.upport

        elif self.destination == MOBOTIX:
            self.createMobotixAccount()
            self.sipNumber = "sip:hanan@10.20.97.222"
            self.downStreamPort = 6600
            # self.upStreamPort = 6700
       # self.listDevices()

    def call(self):
        self.start()
        # Make an outgoing call
        try:
            callUri = self.sipNumber
            self.myCall = ducall.Call(acc=self.acc, peer_uri=callUri, upStreamPort=self.upStreamPort, downStreamPort=self.downStreamPort)
            self.call_param = pj.CallOpParam()
            self.call_param.opt.audioCount = 1
            self.call_param.opt.videoCount = 0
            self.myCall.makeCall(callUri, self.call_param)
            time.sleep(1)
           # m = self.getMedia()
            # am = pj.AudioMedia.typecastFromMedia(m)
            # self.ep.audDevManager().getCaptureDevMedia().startTransmit(am)
        except pj.Error as e:
            print("Error making the call:", str(e))
        while True:
            time.sleep(0.1)
            self.ep.libHandleEvents(10)
            # self.myCall.onCallMediaState(self.call_param)

    def end(self):
        self.ep.libDestroy()



def sendTestFile(fileName="/home/me/work/pjproject/pjsip-apps/src/pygui/playfile"):
    audioData = array('B')
    with open(fileName, "rb") as f:
        audioData.fromfile(f, 96000)
    shift = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        barr = bytes(audioData[shift:shift + 640])
        sock.sendto(barr, ("0.0.0.0", 6700))
        shift += 640
        if shift >= 96000:
            shift = 0
        time.sleep(0.040)

# Run the main loop
try:
    # sendTestFile()
    callTest = CallTest(args.mode)
    callTest.call()
except KeyboardInterrupt:
    print("Exiting...")

# Clean up
callTest.end()

