import errno
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import asyncio
import crc32c
import secrets

from session.channels.base import Channel
from session.channels.control import Control
from session.channels.discovery import Discovery
from session.channels.stats import Stats
from protobuf.steammessages_remoteclient_discovery_pb2 import EStreamTransport
from protobuf.steammessages_remoteplay_pb2 import k_EStreamChannelDiscovery, k_EStreamChannelControl, \
    k_EStreamControlClientHandshake, CClientHandshakeMsg, CStreamingClientHandshakeInfo, \
    k_EStreamChannelStats
from service.common import get_steamid
from session.client import Client
from session.frame import Frame, frame_timestamp
from session.packet import PacketHeader, Packet, PacketType

streaming_client = '/home/pi/.local/share/SteamLink/bin/streaming_client'
ld_library_path = '/home/pi/.local/share/SteamLink/lib'
sdr_config_path = '/home/pi/.local/share/Valve Corporation/SteamLink/sdr_config.txt'


async def session_run_command(ip: str, port: int, transport: int, session_key: bytes) -> int:
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


async def session_run(ip: str, port: int, transport: int, session_key: bytes) -> int:
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        await loop.run_in_executor(executor, lambda: session_worker((ip, port), session_key))
    return 0


def session_worker(host_address: tuple[str, int], auth_token: bytes):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    client = ClientImpl(sock, host_address, auth_token)
    while not client.closed:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.error as e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                continue
            else:
                raise e
        else:
            client.handle_packet(data)


class ClientImpl(Client):

    def __init__(self, sock: socket.socket, addr: tuple[str, int], auth_token: bytes):
        self.sock = sock
        self.closed = False
        self.addr = addr
        self.auth_token = auth_token
        self.src_conn_id = 1 + secrets.randbelow(255)
        self.dst_conn_id = 0
        self.connect_timestamp = 0
        self.send_encrypt_sequence = 0
        self.recv_decrypt_sequence = 0
        self.channels: dict[int, Channel] = {
            k_EStreamChannelDiscovery: Discovery(self, k_EStreamChannelDiscovery),
            k_EStreamChannelControl: Control(self, k_EStreamChannelControl),
            k_EStreamChannelStats: Stats(self, k_EStreamChannelStats),
        }
        self.connection_channel: Channel = Connection(self, k_EStreamChannelDiscovery)
        self.connect()

    def handle_packet(self, data: bytes):
        packet = Packet.parse(data)
        header = packet.header
        if packet.crc_ok is False:
            print('Bad CRC! dropping.')
            return
        elif header.pkt_type != PacketType.UNCONNECTED and header.dst_conn_id != self.src_conn_id:
            print(f'Unmatched connection ID: {header.dst_conn_id}! expect {self.src_conn_id}. dropping.')
            return

        if header.pkt_type in [PacketType.CONNECT, PacketType.CONNECT_ACK, PacketType.DISCONNECT]:
            self.connection_channel.handle_packet(packet)
        else:
            self.channels[header.channel].handle_packet(packet)

    def send_packet(self, has_crc: bool, pkt_type: PacketType, pkt_id: int, channel: int, payload: bytes = b'',
                    pad_to: int = 0):
        send_timestamp = frame_timestamp()
        header = PacketHeader()
        header.has_crc = has_crc
        header.pkt_type = pkt_type
        header.retransmit_count = 0
        header.src_conn_id = self.src_conn_id
        header.dst_conn_id = self.dst_conn_id
        header.channel = channel
        header.fragment_id = 0
        header.pkt_id = pkt_id
        header.send_timestamp = send_timestamp
        packet = Packet(header, payload)
        self.sock.sendto(packet.serialize(pad_to), self.addr)

    def on_connected(self, conn_id: int, timestamp: int):
        self.dst_conn_id = conn_id
        self.connect_timestamp = timestamp
        self.handshake(conn_id, timestamp)

    def on_disconnect(self):
        self.closed = True

    def add_channel(self, channel: int, handler: Channel):
        self.channels[channel] = handler

    def remove_channel_by_index(self, channel: int):
        del self.channels[channel]

    def remove_channel_by_type(self, handler_type: type(Channel)):
        channel_to_remove = -1
        for channel in self.channels:
            if self.channels[channel] is handler_type:
                channel_to_remove = channel
                break
        if channel_to_remove != -1:
            self.remove_channel_by_index(channel_to_remove)

    def connect(self):
        body = int.to_bytes(crc32c.crc32c(b'Connect'), 4, byteorder='little', signed=False)
        pkt_id = self.connection_channel.next_pkt_id()
        self.connection_channel.send_packet(False, PacketType.CONNECT, pkt_id, body)

    def handshake(self, conn_id: int, timestamp: int):
        self.channels[k_EStreamChannelControl].send_reliable(k_EStreamControlClientHandshake,
                                                             CClientHandshakeMsg(info=CStreamingClientHandshakeInfo()))

    def hangup(self):
        self.connection_channel.send_packet(True, PacketType.DISCONNECT, 0)


class Connection(Channel):
    """
    This channel does not exist.
    """

    def handle_frame(self, frame: Frame):
        header = frame.header
        payload = frame.body
        if header.pkt_type == PacketType.CONNECT_ACK:
            self.on_connect_ack(header.pkt_id, header.src_conn_id,
                                int.from_bytes(payload, byteorder='little', signed=False))
        elif header.pkt_type == PacketType.DISCONNECT:
            self.client.on_disconnect()

    def on_connect_ack(self, pkt_id: int, conn_id: int, timestamp: int):
        if pkt_id not in self.sent_packets:
            return
        self.sent_packets.remove(pkt_id)
        self.client.on_connected(conn_id, timestamp)
