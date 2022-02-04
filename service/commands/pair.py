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
        self.enckey = secrets.token_bytes(32)
        self.pin = '%04d' % secrets.randbelow(10000)
        self.ended = False

    async def poll(self):
        while not self.ended:
            message = pairing.authorization_req(self.host.euniverse, 'Microwave Oven', self.enckey, self.pin)
            self.enckey = message.device_token
            self.send_message(k_ERemoteDeviceAuthorizationRequest, message, (self.ip, self.host.connect_port))
            await asyncio.sleep(3)

    async def run(self):
        print(f'Pair with PIN {self.pin}')
        await self.poll()

    def message_received(self, msg_type: ERemoteClientBroadcastMsg, msg: Message, addr: tuple[str, int]) -> bool:
        if msg_type != k_ERemoteDeviceAuthorizationResponse:
            return False
        print(f'message arrived: {msg}')
        if msg.result == k_ERemoteDeviceAuthorizationSuccess:
            common.set_secret_key(self.enckey)
            self.ended = True
        elif msg.result != k_ERemoteDeviceAuthorizationInProgress:
            self.ended = True
        return True
