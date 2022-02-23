from google.protobuf.message import Message
from typing import Set

from session.client import Client
from session.frame import Frame, FrameAssembler, frame_encrypt, frame_timestamp
from session.packet import Packet, PacketType


class Channel:
    frame_assembler = FrameAssembler()
    sent_packets: Set[int]

    def __init__(self, client: Client, channel: int):
        self.client = client
        self.channel = channel
        self.sent_packets = set[int]()
        self._next_pkt_id = 0

    def handle_packet(self, packet: Packet):
        pkt_type = packet.header.pkt_type
        if pkt_type == PacketType.ACK:
            self.on_ack(packet.header.pkt_id, int.from_bytes(packet.body, byteorder='little', signed=False))
        elif pkt_type == PacketType.NACK:
            self.on_nack(packet.header.pkt_id, int.from_bytes(packet.body, byteorder='little', signed=False))
        elif self.frame_assembler.add_packet(packet):
            if packet.header.pkt_type in [PacketType.RELIABLE, PacketType.RELIABLE_FRAG]:
                self.send_ack(packet.header.pkt_id, packet.header.channel)
        else:
            # print(f'Send NACK to {packet.header.pkt_type}')
            if packet.header.pkt_type in [PacketType.RELIABLE, PacketType.RELIABLE_FRAG]:
                self.send_nack(packet.header.pkt_id, packet.header.channel)

        while True:
            frame = self.frame_assembler.poll_frame()
            if not frame:
                break
            self.handle_frame(frame)

    def handle_frame(self, frame: Frame):
        pass

    def on_ack(self, pkt_id: int, timestamp: int):
        if pkt_id not in self.sent_packets:
            return
        self.sent_packets.remove(pkt_id)

    def on_nack(self, pkt_id: int, timestamp: int):
        if pkt_id not in self.sent_packets:
            return
        self.sent_packets.remove(pkt_id)
        print(f'packet {pkt_id} returned nack')

    def send_packet(self, has_crc: bool, pkt_type: PacketType, pkt_id: int, body: bytes = b'', pad_to: int = 0):
        self.client.send_packet(has_crc, pkt_type, pkt_id, self.channel, body, pad_to)

    def next_pkt_id(self) -> int:
        pkt_id = 0
        for i in range(self._next_pkt_id, 65536):
            if i not in self.sent_packets:
                pkt_id = i
                break
        self.sent_packets.add(pkt_id)
        return pkt_id

    def send_ack(self, pkt_id: int, channel: int):
        body = int.to_bytes(frame_timestamp(), 4, byteorder='little', signed=False)
        self.send_packet(True, PacketType.ACK, pkt_id, body)

    def send_nack(self, pkt_id: int, channel: int):
        body = int.to_bytes(frame_timestamp(), 4, byteorder='little', signed=False)
        self.send_packet(True, PacketType.NACK, pkt_id, body)

    def send_reliable(self, msg_type: int, message: Message, pkt_id: int = -1):
        payload = message.SerializeToString()
        if self.frame_should_encrypt(msg_type):
            payload = frame_encrypt(payload, self.client.auth_token, self.client.send_encrypt_sequence)
            self.client.send_encrypt_sequence += 1
        body = int.to_bytes(msg_type, 1, byteorder='little', signed=False) + payload
        if pkt_id == -1:
            pkt_id = self.next_pkt_id()
        self.send_packet(True, PacketType.RELIABLE, pkt_id, body)

    def send_unconnected(self, msg_type: int, payload: bytes, pad_to: int):
        type_bytes = int.to_bytes(msg_type, 1, byteorder='little', signed=False)
        size_bytes = int.to_bytes(len(payload), 4, byteorder='little', signed=True)
        self.send_packet(True, PacketType.UNCONNECTED, 0, type_bytes + size_bytes + payload, pad_to)

    def frame_should_encrypt(self, msg_type: int) -> bool:
        return False
