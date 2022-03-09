import struct

from dataclasses import dataclass
from typing import Optional

from protobuf.steammessages_remoteplay_pb2 import CStartVideoDataMsg
from service.ccrypto import symmetric_decrypt_with_iv
from session.channels.data import Data
from session.client import Client
from session.frame import DataFrameHeader


@dataclass
class VideoFrameHeader:
    sequence: int
    flags: int
    reserved1: int
    reserved2: int

    @property
    def encrypted(self) -> bool:
        return self.flags & 0x20 != 0

    @classmethod
    def parse(cls, data: bytes):
        return VideoFrameHeader(*struct.unpack('<HBHH', data[:7]))


class Video(Data):

    def __init__(self, client: Client, message: CStartVideoDataMsg):
        super().__init__(client, message.channel)

    def handle_data(self, header: Optional[DataFrameHeader], payload: bytes):
        vheader = VideoFrameHeader.parse(payload)
        encrypted = vheader.flags & 0x20
        data = payload[7:]
        if encrypted:
            data = symmetric_decrypt_with_iv(data, bytes(0 for _ in range(0, 16)), self.client.auth_token)
