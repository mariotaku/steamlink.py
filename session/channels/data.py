from typing import Optional

from protobuf.steammessages_remoteplay_pb2 import k_EStreamDataPacket
from session.channels.base import Channel
from session.frame import Frame, DataFrameHeader, FRAME_HEADER_LENGTH
from session.packet import PacketType


class Data(Channel):

    def handle_frame(self, frame: Frame):
        if frame.header.pkt_type != PacketType.UNRELIABLE:
            return
        payload_type = frame.body[0]
        payload = frame.body[1:]
        if payload_type != k_EStreamDataPacket:
            return
        header: Optional[DataFrameHeader] = None
        if len(payload) > FRAME_HEADER_LENGTH:
            header = DataFrameHeader.parse(payload)
            payload = payload[FRAME_HEADER_LENGTH:]
        self.handle_data(header, payload)

    def handle_data(self, header: Optional[DataFrameHeader], payload: bytes):
        pass
