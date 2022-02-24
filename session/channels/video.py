import struct

from typing import Optional

from protobuf.steammessages_remoteplay_pb2 import CStartVideoDataMsg
from service.ccrypto import symmetric_decrypt_with_iv
from session.channels.data import Data
from session.client import Client
from session.frame import DataFrameHeader


class Video(Data):

    def __init__(self, client: Client, message: CStartVideoDataMsg):
        super().__init__(client, message.channel)

    def handle_data(self, header: Optional[DataFrameHeader], payload: bytes):
        sequence, flags, num2, num3 = struct.unpack('<HBHH', payload[:7])
        protected = flags & 0x10
        encrypted = flags & 0x20
        data = payload[7:]
        if encrypted:
            data = symmetric_decrypt_with_iv(data, bytes(0 for _ in range(0, 16)), self.client.auth_token)
