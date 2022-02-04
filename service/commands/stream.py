import secrets

import asyncio
from google.protobuf.message import Message

from protobuf.steammessages_remoteclient_discovery_pb2 import CMsgRemoteClientBroadcastStatus, \
    ERemoteClientBroadcastMsg, k_ERemoteDeviceStreamingRequest, \
    k_ERemoteDeviceStreamingResponse, k_ERemoteDeviceProofRequest, k_ERemoteDeviceStreamingInProgress, \
    k_ERemoteDeviceStreamingSuccess
from service import streaming
from service.commands.base import CliCommand
from service.common import ServiceProtocol


class StreamCommand(CliCommand):
    def __init__(self, protocol: ServiceProtocol, ip: str, host: CMsgRemoteClientBroadcastStatus):
        super().__init__(protocol)
        self.ip = ip
        self.host = host
        self.ended = False

    async def run(self):
        request_id = 1 + secrets.randbelow(0x7fffffff)
        while not self.ended:
            message = streaming.streaming_req(request_id)
            self.send_message(k_ERemoteDeviceStreamingRequest, message, (self.ip, self.host.connect_port))
            await asyncio.sleep(1)

    def message_received(self, msg_type: ERemoteClientBroadcastMsg, msg: Message, addr: tuple[str, int]) -> bool:
        if msg_type == k_ERemoteDeviceProofRequest:
            print(f'device proof request: {msg}')
            return True
        if msg_type != k_ERemoteDeviceStreamingResponse:
            return False
        print(f'message arrived: {msg}')
        if msg.result == k_ERemoteDeviceStreamingSuccess:
            self.ended = True
        elif msg.result != k_ERemoteDeviceStreamingInProgress:
            self.ended = True
        return True
