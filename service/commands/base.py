from google.protobuf.message import Message

from service.common import ServiceProtocol


class CliCommand:

    def __init__(self, protocol: ServiceProtocol):
        self.protocol = protocol

    def parse_args(self, args: list[str]) -> bool:
        pass

    async def run(self):
        pass

    def message_received(self, msg_type: int, msg: Message, addr: tuple[str, int]) -> bool:
        pass

    def send_message(self, msg_type: int, msg: Message, addr: tuple[str, int]):
        self.protocol.send_message(msg_type, msg, addr)
