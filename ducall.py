#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA 
#
import sys
import time

import pjsua2 as pj
import application
from udpsniffer import UdpSniffer
import endpoint as ep
import json
import struct
import queue
import socket
import threading
import logging
import os
import copy

USE_CUSTOM_MEDIA = True

CLOCK_RATE = 16000
CHANNEL_COUNT = 1
BITS_PER_SAMPLE = 16
FRAME_TIME_USEC = 40000
SHARED_VOLUME_PATH = "/tmp/du-sip"


class WatchdogData:
    VALID = 0
    ERRONEOUS = 1
    INTERNAL_INFO = "internal_info"
    INTERNAL_ERROR = "internal_error"
    EXTERNAL_ERROR = "external_error"

    def __init__(self):
        self.state = WatchdogData.VALID
        self.clientStartTime = time.monotonic()
        self.lastFrameRequestedTime = 0
        self.lastFrameReceivedTime = 0
        self.qsize = 0
        self.framesRequested = 0
        self.framesReceived = 0

        self.ipcSocketPath = f"{SHARED_VOLUME_PATH}/ipc.sock"

    def frameRequested(self, qsize, framesRequested):
        self.lastFrameRequestedTime = time.monotonic()
        self.qsize = qsize
        self.framesRequested = framesRequested

    def notifyExternalApp(self, msg_type, content):
        message = {'type': msg_type, 'message': content}
        message_json = json.dumps(message)
        logging.error(f"Got error: {message_json} it will be sent via {self.ipcSocketPath}")

        if not os.path.exists(self.ipcSocketPath):
            logging.error(f"cannot send error notification - socket {self.ipcSocketPath} doesn not exist")
            return

        # Create a Unix domain socket
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            try:
                # Connect to the Unix domain socket
                sock.connect(self.ipcSocketPath)

                # Send the JSON message
                sock.sendall(message_json.encode())
                logging.info(f"Message sent")

            except Exception as e:
                logging.error(f"Error on sending error message: {e}")

    def frameReceived(self, framesReceived):
        self.lastFrameReceivedTime = time.monotonic()
        self.framesReceived = framesReceived

    def callbacksTimeIsValid(self):
        now = time.monotonic()
        runningTime = now - self.clientStartTime
        if int(runningTime) % 30 == 0:
            logging.info(f"=========  Watchdog Check State {runningTime}  =========")
            self.notifyExternalApp(WatchdogData.INTERNAL_INFO, f"Client runs {runningTime} sec. "
                                    f"Requested: {self.framesRequested}, Received  {self.framesReceived} frames")

        if runningTime < 10:
            return True

        if self.lastFrameReceivedTime == 0 or self.lastFrameRequestedTime == 0:
            self.notifyExternalApp(WatchdogData.INTERNAL_ERROR, f"Client runs {runningTime} sec but SIP communication still not started")
            return False

        if (now - self.lastFrameReceivedTime) > 1 or (now - self.lastFrameRequestedTime) > 1:
            self.notifyExternalApp(WatchdogData.INTERNAL_ERROR, "The SIP packets send/receive is timeouted")
            return False

        if self.qsize > 10:
            self.notifyExternalApp(WatchdogData.EXTERNAL_ERROR, f"The to SIP queue size {self.qsize} exceeds the limit")
            return False
        return True

    def checkState(self):
        if self.state == WatchdogData.VALID:
            self.state = WatchdogData.VALID if self.callbacksTimeIsValid() else WatchdogData.ERRONEOUS
            if self.state == WatchdogData.ERRONEOUS:
                logging.critical(f"======================== !!!  Watchdog detected a problem. The client is going to restart!")
            return self.state
        return self.state


class CustomMediaPort(pj.AudioMediaPort):
    def __init__(self,  watchdogData, upStreamPort, downStreamPort, useSniffer=False, playbackFile=None, echoMode=False):
        logging.info(f"CustomMediaPort constructor {id(self)}")
        pj.AudioMediaPort.__init__(self)
        self.watchdogData = watchdogData
        self.frameFromDuCount = 0
        self.frameCount = 0
        self.framesSentCount = 0
        self.frameBuffer = None
        self.framesToSip = queue.Queue()
        self.echoFrames = queue.Queue()
        self.count = 0
        self.downStreamPort = downStreamPort
        self.upStreamPort = upStreamPort
        self.useSniffer = useSniffer
        self.playbackFile = None
        self.echoMode = echoMode
        if playbackFile:
            playbackFile = os.path.join("/tmp/du-sip",playbackFile)
            self.playbackFile = open(playbackFile, "wb")

        self.upStreamSocket = None
        if self.upStreamPort > 0:
            self.upStreamSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            logging.info(f"Created upstream socket. Port {self.upStreamPort}")
        if self.downStreamPort:
            self.downStreamSniffer = UdpSniffer(downStreamPort)
            self.downStreamThread = threading.Thread(target=self.listenForDownStream, daemon=True)
            self.downStreamThread.start()

    def processStreamAsIs(self, data):
        frameBuffer = pj.ByteVector()
        for i in range(len(data)):
            frameBuffer.append(data[i])
        self.framesToSip.put(frameBuffer)
        if self.frameFromDuCount % 50 == 0:
            logging.debug(f"{time.time()} ---- Added Frame As Is {self.frameFromDuCount} qsize: {self.framesToSip.qsize()}")
        self.frameFromDuCount += 1

    def listenForDownStream(self):
        logging.info(f"Downstream listener thread is started")
        self.frameBuffer = pj.ByteVector()
        if self.useSniffer:
            logging.info("Downstream initialized in sniffing mode")
            self.downStreamSniffer.sniff(self.processStreamAsIs)
        else:
            logging.info("Downstream initialized in reading mode")
            self.downStreamSniffer.read(self.processStreamAsIs)


    def onFrameRequested(self, frame):
        qsize = self.framesToSip.qsize()
        self.watchdogData.frameRequested(qsize, self.framesSentCount)
        if qsize > 0:
            frame.type = pj.PJMEDIA_TYPE_AUDIO
            # Get a frame from the queue and pass it to PJSIP
            frame.buf = self.framesToSip.get()
            frame.size = frame.buf.size()

            if self.echoMode:
                barr = bytes(frame.buf)
                self.upStreamSocket.sendto(barr, ("0.0.0.0", self.upStreamPort))
            if self.framesSentCount % 50 == 0:
                logging.debug(f"{time.time()}-------- Frames sent: {self.framesSentCount}, size: {frame.buf.size()}")
            self.framesSentCount += 1
        else:
            frame.type = pj.PJMEDIA_TYPE_NONE
            frame.size = 0
            # self.setEmptyFrame(frame)

    def setEmptyFrame(self, frame):
        frame.buf = pj.ByteVector()
        for i in range(frame.size):
            frame.buf.append(0)

    def createDummyFrameBuffer(self, frameSize):
        frame_ = pj.ByteVector()
        for i in range(frameSize):
            if (i % 2 == 1):
                x = int(np.sin((self.count / 10) % 6) * 10000)
                if (x > 32767):
                    x = 32767
                else:
                    if (x < -32768):
                        x = -32768

                # Convert it to unsigned 16-bit integer
                x = struct.unpack('<H', struct.pack('<h', x))[0]

                # Put it back in the vector in little endian order
                frame_.append(x & 0xff)
                frame_.append((x & 0xff00) >> 8)
                self.count += 1

        return frame_

    def createDummyFrame(self, frame):
        frame.type = pj.PJMEDIA_TYPE_AUDIO
        frame.size = 640
        frame.buf = self.createDummyFrameBuffer(frame.size)


    def onFrameReceived(self, frame):
        self.frameCount += 1
        self.watchdogData.frameReceived(self.frameCount)
        if self.upStreamSocket:
            if self.echoMode:
                    return
            barr = bytes(frame.buf)
            self.upStreamSocket.sendto(barr, ("0.0.0.0", self.upStreamPort))
            # self.playbackFile.write(barr)
            if self.frameCount % 50 == 0:
                logging.debug(f"{time.time()}+++++  on frame received and sent to playback device: {self.frameCount}")
            if self.playbackFile:
                self.playbackFile.write(barr)

        return




# Call class
class Call(pj.Call):
    """
    High level Python Call object, derived from pjsua2's Call object.
    """
    def __init__(self, acc, peer_uri='', chat=None, call_id=pj.PJSUA_INVALID_ID, downStreamPort=0,
                 upStreamPort=0, useSniffer=None, playbackFile=None, sampleRate=None, frameLen=None, echoMode=False):
        global CLOCK_RATE
        global FRAME_TIME_USEC
        pj.Call.__init__(self, acc, call_id)
        self.watchdogData = WatchdogData()
        self.acc = acc
        self.peerUri = peer_uri
        self.chat = chat
        self.connected = False
        self.onhold = False
        self.custom_audio_media = None
        self.secondTime = False
        self.downStreamPort = downStreamPort
        self.upStreamPort = upStreamPort
        self.med_port = None
        self.useSniffer = useSniffer
        self.playbackFile = playbackFile
        if sampleRate:
            CLOCK_RATE = sampleRate
        if frameLen:
            FRAME_TIME_USEC = frameLen * 1000
        self.watchdogThread = threading.Thread(target=self.watchdog, daemon=True)
        self.watchdogThread.start()
        self.echoMode = echoMode

    def watchdog(self):
        while True:
            if (self.watchdogData.checkState() != WatchdogData.VALID):
                os._exit(-1)
            time.sleep(1)

    def getAudioMedia(self):
        ci = self.getInfo()
        for mi in ci.media:
            logging.info(f"type {mi.type}, status {mi.status}")
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and \
              (mi.status != pj.PJSUA_CALL_MEDIA_NONE and \
               mi.status != pj.PJSUA_CALL_MEDIA_ERROR):
                return mi
        return None

    def onCallState(self, prm):
        logging.info(f'XXXX   Call state')
        ci = self.getInfo()
        self.connected = ci.state == pj.PJSIP_INV_STATE_CONFIRMED
        if self.chat:
            self.chat.updateCallState(self, ci)

    def createCustomMediaPort(self):
        if self.med_port:
            return
        fmt = pj.MediaFormatAudio()
        fmt.type = pj.PJMEDIA_TYPE_AUDIO
        fmt.clockRate = CLOCK_RATE
        fmt.channelCount = CHANNEL_COUNT
        fmt.bitsPerSample = BITS_PER_SAMPLE
        fmt.frameTimeUsec = FRAME_TIME_USEC

        self.med_port = CustomMediaPort(watchdogData=self.watchdogData, upStreamPort=self.upStreamPort,
                                        downStreamPort=self.downStreamPort, useSniffer=self.useSniffer,
                                        playbackFile=self.playbackFile, echoMode=self.echoMode)
        self.med_port.createPort("med_port", fmt)


    def createPlayerMedia(self):
        self.custom_audio_media = pj.AudioMediaPlayer()
        self.custom_audio_media.createPlayer("/tmp/playfile")

    def setCustomMedia(self):
        if self.custom_audio_media is not None:
            return
        # self.createPlayerMedia()
        self.createCustomMediaPort()
        mik = ep.Endpoint.instance.audDevManager().getCaptureDevMedia()
        speaker = ep.Endpoint.instance.audDevManager().getPlaybackDevMedia()

        # Create a new call and audio stream
        media = self.getMedia(pj.PJMEDIA_TYPE_AUDIO)
        audio_media = pj.AudioMedia.typecastFromMedia(media)

        # Connect the custom audio media to the audio stream
        self.custom_audio_media.startTransmit(speaker)

    def onCallMediaState(self, prm):
        logging.info(f'Call Media state')
        # We reach this point twice but only second time is important
        if not self.secondTime:
            self.secondTime = True
            return
        # self.firstTime = False
        ci = self.getInfo()
        for mi in ci.media:
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and \
              (mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE or \
               mi.status == pj.PJSUA_CALL_MEDIA_REMOTE_HOLD):
                m = self.getMedia(mi.index)
                am = pj.AudioMedia.typecastFromMedia(m)
                # connect ports

                if USE_CUSTOM_MEDIA:
                    # self.setCustomMedia(am)
                    self.createCustomMediaPort()
                    am.startTransmit(self.med_port)
                    self.med_port.startTransmit(am)

                if not USE_CUSTOM_MEDIA:
                    ep.Endpoint.instance.audDevManager().getCaptureDevMedia().startTransmit(am)
                    am.startTransmit(ep.Endpoint.instance.audDevManager().getPlaybackDevMedia())
                logging.info(f'Call Media state startTransmit {ep} {am} {mi}')

                if mi.status == pj.PJSUA_CALL_MEDIA_REMOTE_HOLD and not self.onhold:
                    self.chat.addMessage(None, "'%s' sets call onhold" % (self.peerUri))
                    self.onhold = True
                elif mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE and self.onhold:
                    self.chat.addMessage(None, "'%s' sets call active" % (self.peerUri))
                    self.onhold = False
        if self.chat:
            self.chat.updateCallMediaState(self, ci)
            logging.info(f'Call Media state updateCallMediaState {ci}')

    def onInstantMessage(self, prm):
        # chat instance should have been initalized
        if not self.chat: return

        self.chat.addMessage(self.peerUri, prm.msgBody)
        self.chat.showWindow()

    def onInstantMessageStatus(self, prm):
        if prm.code/100 == 2: return
        # chat instance should have been initalized
        if not self.chat: return

        self.chat.addMessage(None, "Failed sending message to '%s' (%d): %s" % (self.peerUri, prm.code, prm.reason))

    def onTypingIndication(self, prm):
        # chat instance should have been initalized
        if not self.chat: return

        self.chat.setTypingIndication(self.peerUri, prm.isTyping)

    def onDtmfDigit(self, prm):
        pass

    def onCallMediaTransportState(self, prm):
        pass


if __name__ == '__main__':
    application.main()
