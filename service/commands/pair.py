import asyncio
import secrets
from google.protobuf.message import Message

from protobuf.steammessages_remoteclient_discovery_pb2 import CMsgRemoteClientBroadcastStatus, \
    k_ERemoteDeviceAuthorizationRequest, ERemoteClientBroadcastMsg, k_ERemoteDeviceAuthorizationResponse, \
    k_ERemoteDeviceAuthorizationInProgress, k_ERemoteDeviceAuthorizationSuccess
from service import pairing, common
from service.commands.base import CliCommand
from service.common import ServiceProtocol


class PairCommand(CliCommand):
    def __init__(self, protocol: ServiceProtocol, ip: str, host: CMsgRemoteClientBroadcastStatus):
        super().__init__(protocol)
        self.ip = ip
        self.host = host
        self.ended = False

    async def run(self):
        enckey = common.get_secret_key()
        pin = '%04u' % secrets.randbelow(10000)
        print(f'Pair with PIN {pin}')
        while not self.ended:
            message = pairing.authorization_req(self.host.euniverse, 'Microwave Oven', enckey, pin)
            self.send_message(k_ERemoteDeviceAuthorizationRequest, message, (self.ip, self.host.connect_port))
            await asyncio.sleep(3)

    def message_received(self, header: Message, msg: Message, addr: tuple[str, int]) -> bool:
        if header.msg_type != k_ERemoteDeviceAuthorizationResponse:
            return False
        print(f'message arrived: {msg}')
        if msg.result == k_ERemoteDeviceAuthorizationSuccess:
            common.set_steamid(msg.steamid)
            self.ended = True
        elif msg.result != k_ERemoteDeviceAuthorizationInProgress:
            self.ended = True
        return True
