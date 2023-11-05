import pjsua2 as pj
import time
import socket
from array import array
import argparse
import sys

import settings
import ducall
import log
import endpoint as ep


MOBOTIX = "mobotix"
TSYSTEMS = "tsystems"

write=sys.stdout.write

parser = argparse.ArgumentParser()

parser.add_argument("--profile", choices=[MOBOTIX, TSYSTEMS], default=MOBOTIX)
parser.add_argument("--sip-number", default="")
parser.add_argument("--downport", type=int, default=6600, help="UDP port for PCM stream from Streamer to SIP server")
parser.add_argument("--upport", type=int, default=6700, help="UDP port for PCM stream from SIP server to Streamer")
parser.add_argument("--use-sniffer", action="store_true", help="When defined the downstream socket will work in sniff mode. It allows to read the data when when port is used by other apps")

args = parser.parse_args()


# Create a custom account class to handle account events
class MyAccount(pj.Account):
    def __init__(self):
        pj.Account.__init__(self)

    def onRegState(self, prm):
        if prm.code == 200:
            print("Registration successful")


class CallTest:
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
        audio_dev_man = self.ep.audDevManager()

        # Print the list of audio input (capture) devices
        for i in range(0, audio_dev_man.getDevCount()):
            devInfo = audio_dev_man.getDevInfo(i)
            print(f"#{i}) {devInfo.name} inp: {devInfo.inputCount} out: {devInfo.outputCount}")

    def setSipNumber(self, defaultSipNumber):
        if args.sip_number == "":
            self.sipNumber = defaultSipNumber
        else:
            self.sipNumber = "sip:" + args.sip_number
        print(f"Sip number is: {self.sipNumber}")

    def createMobotixAccount(self):
        self.acfg = pj.AccountConfig()
        self.acfg.idUri = "sip:driveu@10.20.97.100"
        cred = pj.AuthCredInfo("digest", "*", "driveu", 0, "")
        self.acfg.sipConfig.authCreds.append(cred)
        # Create the account
        self.acc = pj.Account()
        self.acc.cfg = self.acfg
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
        try:
            self.acc.setRegistration(True)
        except pj.Error as error:
            write("Exception:\r\n")
            write("  ," + error.info() + "\r\n")
            write("Traceback:\r\n")
            log.writeLog2(1, 'Exception: ' + error.info() + '\n')
        except Exception as error:
            write("Exception:\r\n")
            write("  ," +  str(error) + "\r\n")
            write("Traceback:\r\n")
            write(traceback.print_stack())
        print("XXXXXXXXX Set registration")

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
        if self.profile == TSYSTEMS:
            self.createTsystemAccount()
            self.setSipNumber(defaultSipNumber="sip:100@localhost")
            self.downStreamPort = args.downport
            self.upStreamPort = args.upport
            print(f"Set SIP T-Systems profile:  "
                  f"\n\tnumber {self.sipNumber}"
                  f"\n\tdown stream port {self.downStreamPort}"
                  f"\n\tup stream port {self.upStreamPort}")

        elif self.profile == MOBOTIX:
            self.createMobotixAccount()
            self.setSipNumber(defaultSipNumber="sip:100@10.20.97.222")
            self.downStreamPort = args.downport
            # self.upStreamPort = args.upport
       # self.listDevices()
        audio_dev_man = self.ep.audDevManager()
        audio_dev_man.setNullDev()

    def call(self):
        self.start()
        # Make an outgoing call
        try:
            callUri = self.sipNumber
            self.myCall = ducall.Call(acc=self.acc, peer_uri=callUri, upStreamPort=self.upStreamPort, downStreamPort=self.downStreamPort, useSniffer=args.use_sniffer)
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
    callTest = CallTest(args.profile)
    callTest.call()
except KeyboardInterrupt:
    print("Exiting...")

# Clean up
callTest.end()

