import asyncio
import secrets
from argparse import ArgumentParser
from google.protobuf.message import Message

from protobuf.steammessages_remoteclient_discovery_pb2 import CMsgRemoteClientBroadcastStatus, \
    k_ERemoteDeviceStreamingRequest, \
    k_ERemoteDeviceStreamingResponse, k_ERemoteDeviceProofRequest, k_ERemoteDeviceStreamingInProgress, \
    k_ERemoteDeviceStreamingSuccess, CMsgRemoteClientBroadcastHeader, k_ERemoteDeviceProofResponse, \
    CMsgRemoteDeviceProofResponse, k_ERemoteDeviceStreamingFailed
from service import streaming, ccrypto
from service.commands.base import CliCommand
from service.common import ServiceProtocol, get_secret_key
from session.client_impl import session_run, session_run_command


class StreamCommand(CliCommand):
    ip: str
    header: CMsgRemoteClientBroadcastHeader
    host: CMsgRemoteClientBroadcastStatus
    native: bool

    def __init__(self, protocol: ServiceProtocol):
        super().__init__(protocol)
        self.header = None
        self.host = None
        self.ended = False
        self.request_id = 1 + secrets.randbelow(0x7fffffff)
        self.streaming_info = None
        self.native = False

    def parse_args(self, argv: list[str]) -> bool:
        stream = ArgumentParser('stream')
        stream.add_argument('-n', '--native', dest='native', action='store_true', default=False)
        stream.add_argument('ip', nargs='?', type=str, default='192.168.4.16')
        args = stream.parse_args(argv)
        ip = args.ip
        header, host = self.protocol.discovered.get(ip, (None, None))
        if not host:
            print(f'Host info not available for {ip}')
            return False
        self.ip = ip
        self.header = header
        self.host = host
        self.native = args.native
        return True

    async def run(self):
        message = streaming.streaming_req(self.request_id, self.header.client_id)
        while not self.ended:
            self.send_message(k_ERemoteDeviceStreamingRequest, message, (self.ip, self.host.connect_port))
            await asyncio.sleep(1)
        if self.streaming_info:
            session_key = ccrypto.symmetric_decrypt(self.streaming_info.encrypted_session_key, get_secret_key())
            if self.native:
                retval = await session_run_command(self.ip, self.streaming_info.port, self.streaming_info.transport,
                                                   session_key)
            else:
                retval = await session_run(self.ip, self.streaming_info.port, self.streaming_info.transport,
                                           session_key)
            print(f'client exited with code {retval}')

    def gen_proof_response(self, challenge: bytes) -> Message:
        encrypted = ccrypto.symmetric_encrypt(challenge, get_secret_key())
        return CMsgRemoteDeviceProofResponse(request_id=self.request_id, response=encrypted)

    def message_received(self, header: Message, msg: Message, addr: tuple[str, int]) -> bool:
        msg_type = header.msg_type
        if msg_type == k_ERemoteDeviceProofRequest:
            if self.request_id == msg.request_id:
                resp = self.gen_proof_response(msg.challenge)
            else:
                self.ended = True
                resp = CMsgRemoteDeviceProofResponse(response=b'')
            self.send_message(k_ERemoteDeviceProofResponse, resp, addr)
            return True
        if msg_type != k_ERemoteDeviceStreamingResponse:
            return False
        if msg.result == k_ERemoteDeviceStreamingSuccess:
            self.streaming_info = msg
            self.ended = True
        if msg.result == k_ERemoteDeviceStreamingFailed:
            self.ended = True
        elif msg.result != k_ERemoteDeviceStreamingInProgress:
            self.ended = True
        return True
