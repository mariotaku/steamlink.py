import os
import subprocess
import sys

import secrets

import asyncio
from google.protobuf.message import Message
from os import environ

from protobuf.steammessages_remoteclient_discovery_pb2 import CMsgRemoteClientBroadcastStatus, \
    ERemoteClientBroadcastMsg, k_ERemoteDeviceStreamingRequest, \
    k_ERemoteDeviceStreamingResponse, k_ERemoteDeviceProofRequest, k_ERemoteDeviceStreamingInProgress, \
    k_ERemoteDeviceStreamingSuccess, CMsgRemoteClientBroadcastHeader, k_ERemoteDeviceProofResponse, \
    CMsgRemoteDeviceProofResponse, EStreamTransport
from service import streaming, ccrypto
from service.commands.base import CliCommand
from service.common import ServiceProtocol, get_secret_key, get_steamid

streaming_client = '/home/pi/.local/share/SteamLink/bin/streaming_client'
ld_library_path = '/home/pi/.local/share/SteamLink/lib'
sdr_config_path = '/home/pi/.local/share/Valve Corporation/SteamLink/sdr_config.txt'


class StreamCommand(CliCommand):
    def __init__(self, protocol: ServiceProtocol, ip: str, header: CMsgRemoteClientBroadcastHeader,
                 host: CMsgRemoteClientBroadcastStatus):
        super().__init__(protocol)
        self.ip = ip
        self.header = header
        self.host = host
        self.ended = False
        self.request_id = 1 + secrets.randbelow(0x7fffffff)
        self.streaming_info = None

    async def run(self):
        message = streaming.streaming_req(self.request_id, self.header.client_id)
        while not self.ended:
            self.send_message(k_ERemoteDeviceStreamingRequest, message, (self.ip, self.host.connect_port))
            await asyncio.sleep(1)
        if self.streaming_info:
            transport = EStreamTransport.Name(self.streaming_info.transport)
            server = f'{self.ip}:{self.streaming_info.port}'
            session_key = ccrypto.symmetric_decrypt(self.streaming_info.encrypted_session_key, get_secret_key())
            args = ['--sdr_config', sdr_config_path, '--burst', '150000', '--captureres', '1920x1080',
                    '--performance-icons', '--performance-overlay', '--enable-microphone',
                    '--transport', transport, '--steamid', str(get_steamid()),
                    '--server', server, session_key[0:16].hex()]
            env = {
                'LD_LIBRARY_PATH': ld_library_path,
                'XDG_RUNTIME_DIR': '/run/user/1000'
            }
            print(f'Run with options: {" ".join(args)}')
            proc = await asyncio.create_subprocess_exec(streaming_client, *args, env=env, stdin=subprocess.PIPE,
                                                        stdout=sys.stderr, stderr=sys.stderr)
            print(f'client exited with code {await proc.wait()}')

    def gen_proof_response(self, challenge: bytes) -> Message:
        encrypted = ccrypto.symmetric_encrypt(challenge, get_secret_key())
        return CMsgRemoteDeviceProofResponse(request_id=self.request_id, response=encrypted)

    def message_received(self, header: Message, msg: Message, addr: tuple[str, int]) -> bool:
        msg_type = header.msg_type
        if msg_type == k_ERemoteDeviceProofRequest:
            print(f'device proof request: {msg}')
            if self.request_id == msg.request_id:
                resp = self.gen_proof_response(msg.challenge)
            else:
                self.ended = True
                resp = CMsgRemoteDeviceProofResponse(response=b'')
            self.send_message(k_ERemoteDeviceProofResponse, resp, addr)
            return True
        if msg_type != k_ERemoteDeviceStreamingResponse:
            return False
        print(f'message arrived: {msg}')
        if msg.result == k_ERemoteDeviceStreamingSuccess:
            self.streaming_info = msg
            self.ended = True
        elif msg.result != k_ERemoteDeviceStreamingInProgress:
            self.ended = True
        return True
