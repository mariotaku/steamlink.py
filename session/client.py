import time

import crc32c
import secrets
import struct
import subprocess
import sys
from concurrent.futures import Future

import asyncio
from asyncio import DatagramTransport

from protobuf.steammessages_remoteclient_discovery_pb2 import EStreamTransport
from protobuf.steammessages_remoteplay_pb2 import k_EStreamChannelDiscovery
from service import ccrypto
from service.common import get_secret_key, get_steamid

streaming_client = '/home/pi/.local/share/SteamLink/bin/streaming_client'
ld_library_path = '/home/pi/.local/share/SteamLink/lib'
sdr_config_path = '/home/pi/.local/share/Valve Corporation/SteamLink/sdr_config.txt'


async def session_run(ip: str, port: int, transport: int, session_key: bytes) -> int:
    # return await session_run_shell(ip, port, transport, session_key)
    loop = asyncio.get_event_loop()
    cond = loop.create_future()
    transport, protocol = await loop.create_datagram_endpoint(lambda: SessionProtocol((ip, port), cond),
                                                              local_addr=('0.0.0.0', 0))
    try:
        await cond
    finally:
        transport.close()


async def session_run_shell(ip, port, transport, session_key):
    transport_name = EStreamTransport.Name(transport)
    server = f'{ip}:{port}'
    args = ['--sdr_config', sdr_config_path, '--burst', '150000', '--captureres', '1920x1080',
            '--performance-icons', '--performance-overlay', '--enable-microphone',
            '--transport', transport_name, '--steamid', str(get_steamid()),
            '--server', server, session_key.hex()]
    env = {
        'LD_LIBRARY_PATH': ld_library_path,
        'XDG_RUNTIME_DIR': '/run/user/1000'
    }
    print(f'Run with options: {" ".join(args)}')
    proc = await asyncio.create_subprocess_exec(streaming_client, *args, env=env, stdin=subprocess.PIPE,
                                                stdout=sys.stderr, stderr=sys.stderr)
    return await proc.wait()


class SessionProtocol(asyncio.DatagramProtocol):
    transport: DatagramTransport

    def __init__(self, addr: tuple[str, int], cond: Future):
        super().__init__()
        self.addr = addr
        self.cond = cond
        self.src_conn_id = 0
        self.dst_conn_id = 0

    def connection_made(self, transport: DatagramTransport) -> None:
        self.transport = transport
        self.src_conn_id = 1 + secrets.randbelow(255)
        self.send_packet(1, False, k_EStreamChannelDiscovery, int.to_bytes(crc32c.crc32c(b'Connect'), 4,
                                                                           byteorder='little', signed=False))

    def send_packet(self, msg_type: int, has_crc: bool, channel: int, payload: bytes):
        send_timestamp = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1000) & 0xFFFFFFFF
        packet = struct.pack('<1B', msg_type | 0x80 if has_crc else msg_type)
        packet += struct.pack('<1B', 0)  # retransmit_count
        packet += struct.pack('<1B', self.src_conn_id)
        packet += struct.pack('<1B', self.dst_conn_id)
        packet += struct.pack('<1B', channel)
        packet += struct.pack('<1h', 0)  # fragment_id
        packet += struct.pack('<1H', 0)  # packet_id
        packet += struct.pack('<1I', send_timestamp)
        packet += payload
        if has_crc:
            packet += struct.pack('<1I', crc32c.crc32c(packet))
        print(f'send packet {msg_type} to {self.addr[0]}:{self.addr[1]}')
        self.transport.sendto(packet, self.addr)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        offset = 0
        type_and_crc, = struct.unpack_from('<B', data, offset)
        msg_type = type_and_crc & 0x7F
        has_crc = type_and_crc & 0x80 != 0
        print(f'msg_type={msg_type}, has_crc={has_crc}')
        pass

# TODO handle ping/pong on channel 0
# TODO send auth request
# TODO handle auth response
# TODO handle
