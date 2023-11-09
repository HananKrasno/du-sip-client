import socket
import struct
import time


class UdpSniffer:
    APv4_PROTOCOL = 0x0800
    IP_UDP_PROTOCOL = 17

    def __init__(self, port=6600):
        self._port = port

    def read(self, dataProcessor):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self._port))
        while True:
            raw_data, addr = sock.recvfrom(1024)
            dataProcessor(raw_data)

    def sniff(self, dataProcessor):
        snifferSocket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(3))
        snifferSocket.bind(("lo", 0))
        pktCount = 0
        print("Started")
        while True:
            raw_data, addr = snifferSocket.recvfrom(1024)
            # print(f"UDP sniffer started on interface: {addr}")
            if UdpSniffer.pktProtocol(addr) != self.APv4_PROTOCOL or UdpSniffer.pktInterfaceIndex(addr) != 0:
                continue
            # Parse IP header
            if UdpSniffer.ipProtocol(raw_data) == self.IP_UDP_PROTOCOL:
                # Parse UDP header
                udp_header = raw_data[34:42]
                udp_header_data = struct.unpack('!HHHH', udp_header)
                udp_src_port = udp_header_data[0]
                udp_dest_port = udp_header_data[1]

                # print(f"ports: {udp_header_data[0]} {udp_header_data[1]}")
                # Extract UDP payload
                if udp_dest_port == self._port:
                    udp_payload = raw_data[42:]
                    dataProcessor(udp_payload)

    @staticmethod
    def pktProtocol(addr):
        return addr[1]

    @staticmethod
    def pktInterfaceIndex(addr):
        return addr[2]

    @staticmethod
    def ipProtocol(raw_data):
        ip_header = raw_data[14:34]
        ip_header_data = struct.unpack('!BBHHHBBH4s4s', ip_header)
        ip_protocol = ip_header_data[6]
        return ip_protocol

def processData(data):
    print(f"{time.time()} Got data. Len is {len(data)}")


def playFile(fileName, frameSize, framePeriod):
    data = []
    f = open(fileName, "rb")
    data.append(f.read(frameSize))
    chunk = f.read(frameSize)
    while chunk:
        data.append(chunk)
        chunk = f.read(frameSize)
    port = 6700
    upStreamSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"Created upstream socket. Port {port}")
    i = 0
    for frame in data:
        upStreamSocket.sendto(frame, ("0.0.0.0", port))
        time.sleep(framePeriod - 0.001)
        print(f"Sent packet {i}")
        i += 1
    print ("============= Done ===============")
# playFile("/home/me/work/du-sip-client/playback")
playFile("/home/me/Downloads/playback", 640 * 2, 0.040)
# sniffer = UdpSniffer(6600)
# sniffer.read(processData)
# sniffer.sniff(processData)
