import struct
import time

import queue
from Crypto.Hash import HMAC, MD5, SHA256
from dataclasses import dataclass
from queue import Queue
from typing import Optional, Dict, Tuple

from protobuf.steammessages_remoteplay_pb2 import k_EStreamControlAuthenticationResponse, \
    k_EStreamControlAuthenticationRequest, k_EStreamControlServerHandshake, k_EStreamControlClientHandshake, \
    k_EStreamChannelDataChannelStart
from service import ccrypto
from session.packet import PacketHeader, Packet, PacketType

FRAME_HEADER_LENGTH = 12


def frame_should_encrypt(msg_type: int) -> bool:
    return msg_type not in [k_EStreamControlClientHandshake, k_EStreamControlServerHandshake,
                            k_EStreamControlAuthenticationRequest, k_EStreamControlAuthenticationResponse]


def frame_encrypt(data: bytes, key: bytes, sequence: int) -> bytes:
    plain = int.to_bytes(sequence, 8, byteorder='little', signed=False) + data
    iv = HMAC.new(key, plain, MD5).digest()
    return iv + ccrypto.symmetric_encrypt_with_iv(plain, iv, key, False)


def frame_decrypt(encrypted: bytes, key: bytes, expect_sequence: int) -> bytes:
    iv = encrypted[0:16]
    plain = ccrypto.symmetric_decrypt_with_iv(encrypted[16:], iv, key)
    HMAC.new(key, plain, MD5).verify(iv)
    if expect_sequence >= 0:
        actual_sequence = int.from_bytes(plain[:8], byteorder='little', signed=False)
        if expect_sequence != actual_sequence:
            raise ValueError(f'Expected sequence {expect_sequence}, actual {actual_sequence}')
    return plain[8:]


def frame_hmac256(data: bytes, key: bytes) -> bytes:
    return HMAC.new(key, data, SHA256).digest()


def frame_timestamp_from_secs(timestamp: float) -> int:
    return int(timestamp * 65536) & 0xFFFFFFFF


def frame_timestamp():
    return frame_timestamp_from_secs(time.clock_gettime(time.CLOCK_MONOTONIC))


@dataclass
class Frame:
    header: PacketHeader
    body: bytes
    completed: bool = True
    frag_count: int = 0
    expected_sequence: int = 0

    def append_packet(self, packet: Packet) -> bool:
        if self.completed or self.frag_count != packet.header.fragment_id:
            return False
        self.body += packet.body
        self.frag_count += 1
        if self.frag_count == self.header.fragment_id:
            self.completed = True
        return True


@dataclass
class DataFrameHeader:
    id: int
    timestamp: int
    input_mark: int
    input_recv_timestamp: int

    @classmethod
    def parse(cls, data: bytes):
        return DataFrameHeader(*struct.unpack('<HIHI', data[:FRAME_HEADER_LENGTH]))


class FrameAssembler:
    frame_queue: Queue[Frame] = Queue()
    temp_frame: Optional[Frame] = None
    packet_headers: Dict[Tuple[int, int], PacketHeader] = {}

    def add_packet(self, packet: Packet) -> bool:
        header = packet.header
        pkt_type = header.pkt_type
        if self.is_packet_handled(header):
            return False
        self.add_handled_packet(header)
        if pkt_type in [PacketType.RELIABLE, PacketType.UNRELIABLE]:
            if self.temp_frame:
                print(
                    f'Message {packet.body[0]} (retransmit: {header.retransmit_count}) in channel {header.channel} already present in temp_frames')
                return False
            frame = Frame(header, packet.body, header.fragment_id == 0)
            if frame.completed:
                self.frame_queue.put_nowait(frame)
            else:
                self.temp_frame = frame
        elif pkt_type in [PacketType.RELIABLE_FRAG, PacketType.UNRELIABLE_FRAG]:
            frame = self.temp_frame
            if not frame:
                print(f'No temp frame found for message in channel {header.channel}')
                return False
            elif not frame.append_packet(packet):
                print(f'Failed to append packet in channel {header.channel}')
                return False
            elif frame.completed:
                self.frame_queue.put_nowait(frame)
                self.temp_frame = None
        else:
            assert header.fragment_id == 0, f'Packet {header.pkt_type} has fragment_id {header.fragment_id}'
            frame = Frame(header, packet.body)
            if frame.completed:
                self.frame_queue.put_nowait(frame)
        return True

    def poll_frame(self) -> Optional[Frame]:
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            pass
        return None

    def is_packet_handled(self, header: PacketHeader) -> bool:
        handled = self.packet_headers.get((header.type_and_crc, header.pkt_id), None)
        return handled and header.send_timestamp - handled.send_timestamp < 10000

    def add_handled_packet(self, header: PacketHeader):
        self.packet_headers[(header.type_and_crc, header.pkt_id)] = header
