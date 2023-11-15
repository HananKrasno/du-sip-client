#
# pjsua Python GUI Demo
#
# Copyright (C)2013 Teluu Inc. (http://www.teluu.com)
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
import struct
import queue
import socket
import threading
import logging
import os


USE_CUSTOM_MEDIA = True

CLOCK_RATE = 16000
CHANNEL_COUNT = 1
BITS_PER_SAMPLE = 16
FRAME_TIME_USEC = 40000


class DriveUMediaPort(pj.AudioMediaPort):
    def __init__(self, upStreamPort, downStreamPort, useSniffer=False, playbackFile=None):
        logging.info(f"DriveUMediaPort constructor {id(self)}")
        pj.AudioMediaPort.__init__(self)
        self.frameFromDuCount = 0
        self.frameCount = 0
        self.framesSentCount = 0
        self.frameBuffer = None
        self.framesToSip = queue.Queue()
        self.framesFromSip = queue.Queue()
        self.count = 0
        self.downStreamPort = downStreamPort
        self.upStreamPort = upStreamPort
        self.useSniffer = useSniffer
        self.playbackFile = None
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



    def processStream(self, data):
        frameBuf = []
        # logging.info("processStream")
        for i in range(len(data)):
            if (i % 2 == 1):
                # Convert it to signed 16-bit integer
                x = data[i] << 8 | data[i-1]
                x = struct.unpack('<h', struct.pack('<H', x))[0]
                frameBuf.append(x)
        # logging.info(f"-------------- frame {self.frameCount} received. Size: {frameBuf}")
        for i in range(0, len(data), 2):
            self.frameBuffer.append(data[i])
            self.frameBuffer.append(data[i + 1])
            if self.frameBuffer.size() == 640:
                self.framesToSip.put(self.frameBuffer)
                if self.frameFromDuCount % 50 == 0:
                    logging.debug(f"---- Added Frame {self.frameFromDuCount}")
                self.frameFromDuCount += 1
                self.frameBuffer = pj.ByteVector()

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
        # self.downStreamSniffer.sniff(self.processStream)

    def onFrameRequested(self, frame):
        qsize = self.framesToSip.qsize()
        if qsize > 0:
            frame.type = pj.PJMEDIA_TYPE_AUDIO
            # Get a frame from the queue and pass it to PJSIP
            frame.buf = self.framesToSip.get()
            frame.size = frame.buf.size()
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
        if self.upStreamSocket:
            barr = bytes(frame.buf)
            self.upStreamSocket.sendto(barr, ("0.0.0.0", self.upStreamPort))
            # self.playbackFile.write(barr)
            if self.frameCount % 50 == 0:
                logging.debug(f"{time.time()}+++++  on frame received and sent to playback device: {self.frameCount}")
            if self.playbackFile:
                self.playbackFile.write(barr)

            # logging.info(f"Sent frame to DriveU port: {self.upStreamPort} data: {barr[100:]}")
        return




# Call class
class Call(pj.Call):
    """
    High level Python Call object, derived from pjsua2's Call object.
    """
    def __init__(self, acc, peer_uri='', chat=None, call_id=pj.PJSUA_INVALID_ID, downStreamPort=0,
                 upStreamPort=0, useSniffer=None, playbackFile=None, sampleRate=None, frameLen=None):
        global CLOCK_RATE
        global FRAME_TIME_USEC
        pj.Call.__init__(self, acc, call_id)
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

        self.med_port = DriveUMediaPort(upStreamPort=self.upStreamPort, downStreamPort=self.downStreamPort, useSniffer=self.useSniffer, playbackFile=self.playbackFile)
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
        # self.custom_audio_media.startTransmit(speaker)
        # mik.startTransmit(self.custom_audio_media)
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
        #msgbox.showinfo("pygui", 'Got DTMF:' + prm.digit)
        pass

    def onCallMediaTransportState(self, prm):
        #msgbox.showinfo("pygui", "Media transport state")
        pass


if __name__ == '__main__':
    application.main()
