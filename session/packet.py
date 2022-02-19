import struct

from crc32c import crc32c
from dataclasses import dataclass, astuple
from enum import Enum
from typing import Optional

PACKET_HEADER_LENGTH = 13


class PacketType(Enum):
    UNCONNECTED = 0
    CONNECT = 1
    CONNECT_ACK = 2
    UNRELIABLE = 3
    UNRELIABLE_FRAG = 4
    RELIABLE = 5
    RELIABLE_FRAG = 6
    ACK = 7
    NACK = 8
    DISCONNECT = 9


@dataclass()
class PacketHeader:
    type_and_crc: int = 0
    retransmit_count: int = 0
    src_conn_id: int = 0
    dst_conn_id: int = 0
    channel: int = 0
    fragment_id: int = 0
    pkt_id: int = 0
    send_timestamp: int = 0

    @property
    def pkt_type(self) -> PacketType:
        return PacketType(self.type_and_crc & 0x7F)

    @pkt_type.setter
    def pkt_type(self, pkt_type: PacketType):
        self.type_and_crc = (self.type_and_crc & 0x80) | (pkt_type.value & 0x7F)

    @property
    def has_crc(self) -> bool:
        return self.type_and_crc & 0x80 != 0

    @has_crc.setter
    def has_crc(self, has_crc: bool):
        self.type_and_crc = (self.type_and_crc & 0x7F) | (0x80 if has_crc else 0x0)

    def serialize(self) -> bytes:
        return struct.pack('<BBBBBhHI', *astuple(self))

    @classmethod
    def parse(cls, data: bytes):
        return PacketHeader(*struct.unpack('<BBBBBhHI', data[:PACKET_HEADER_LENGTH]))


@dataclass()
class Packet:
    header: PacketHeader
    body: bytes
    crc_ok: Optional[bool] = None

    def serialize(self, pad_to: int = 0) -> bytes:
        data = self.header.serialize()
        data += self.body
        if pad_to > 0 and len(data) < pad_to:
            data += bytes([0xFE for _ in range(0, pad_to - len(data))])
        if self.header.has_crc:
            data += int.to_bytes(crc32c(data), length=4, byteorder='little', signed=False)
        return data

    @classmethod
    def parse(cls, data: bytes):
        header = PacketHeader.parse(data)
        body = data[PACKET_HEADER_LENGTH:-4 if header.has_crc else None]
        crc_ok = None
        if header.has_crc:
            crc_ok = crc32c(data[:-4]) == int.from_bytes(data[-4:None], byteorder='little', signed=False)
        return Packet(header, body, crc_ok)
