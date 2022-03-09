from asyncio import AbstractEventLoop

from session.packet import PacketType


class Client:

    def __init__(self, loop: AbstractEventLoop):
        self.closed: bool = False
        self.loop: AbstractEventLoop = loop

    def on_connected(self, conn_id: int, timestamp: int):
        pass

    def on_disconnect(self):
        pass

    def send_packet(self, has_crc: bool, pkt_type: PacketType, pkt_id: int, channel: int, payload: bytes = b'',
                    pad_to: int = 0):
        pass
