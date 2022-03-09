import dpkt as dpkt
from typing import Optional

from protobuf.steammessages_remoteplay_pb2 import k_EStreamDataPacket
from session.channels.video import VideoFrameHeader
from session.frame import FrameAssembler, Frame, DataFrameHeader, FRAME_HEADER_LENGTH
from session.packet import Packet


def handle_frame(frame: Frame) -> bytes:
    payload_type = frame.body[0]
    payload = frame.body[1:]
    if payload_type != k_EStreamDataPacket:
        return bytes([])
    header: Optional[DataFrameHeader] = None
    if len(payload) > FRAME_HEADER_LENGTH:
        header = DataFrameHeader.parse(payload)
        payload = payload[FRAME_HEADER_LENGTH:]
    vheader = VideoFrameHeader.parse(payload)
    if vheader.encrypted:
        print('Frame is encrypted')
        return bytes([])
    return payload[7:]


def parse_pcap(pcap: dpkt.pcap.Reader):
    with open('/tmp/parser_ihs2.h264', 'wb') as f:
        channel = 4
        asm = FrameAssembler(channel)
        for timestamp, buf in pcap:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP):
                continue
            ip = eth.data
            if not isinstance(ip.data, dpkt.udp.UDP):
                continue
            udp = ip.data
            if udp.sport != 27031:
                continue
            pkt = Packet.parse(udp.data)
            if not pkt.crc_ok or pkt.header.channel != channel:
                continue
            asm.add_packet(pkt)
            frame = asm.poll_frame()
            if not frame:
                continue
            f.write(handle_frame(frame))
            f.flush()


if __name__ == '__main__':

    with open('wireshark/ihslib_sess2.pcap', 'rb') as f:
        parse_pcap(dpkt.pcap.Reader(f))
