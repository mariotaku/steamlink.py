import errno
import socket
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import asyncio
import crc32c
import secrets
from google.protobuf.message import Message, DecodeError

from protobuf.steammessages_remoteclient_discovery_pb2 import EStreamTransport, k_EStreamDeviceFormFactorTV
from protobuf.steammessages_remoteplay_pb2 import k_EStreamChannelDiscovery, k_EStreamChannelControl, \
    k_EStreamControlAuthenticationResponse, CAuthenticationResponseMsg, CNegotiationInitMsg, \
    k_EStreamControlNegotiationInit, CNegotiationSetConfigMsg, k_EStreamControlNegotiationSetConfig, \
    k_EStreamControlNegotiationComplete, CNegotiationCompleteMsg, k_EStreamControlAuthenticationRequest, \
    CAuthenticationRequestMsg, k_EStreamControlClientHandshake, CClientHandshakeMsg, CStreamingClientHandshakeInfo, \
    k_EStreamControlServerHandshake, k_EStreamDiscoveryPingRequest, \
    CDiscoveryPingRequest, CDiscoveryPingResponse, k_EStreamDiscoveryPingResponse, CServerHandshakeMsg, \
    CNegotiatedConfig, CStreamVideoMode, CStreamingClientConfig, CStreamingClientCaps, k_EStreamAudioCodecOpus, \
    k_EStreamVideoCodecH264, k_EStreamVideoCodecHEVC, k_EStreamVersionCurrent
from service.common import get_steamid
from session.frame import frame_should_encrypt, frame_encrypt, frame_decrypt, frame_hmac256, frame_timestamp_from_secs

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


def session_worker(host_address: tuple[str, int], auth_token: bytes):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    worker = SessionWorker(sock, host_address, auth_token)
    while not worker.closed:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.error as e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                continue
            else:
                raise e
        else:
            worker.handle_packet(data)


class SessionWorker:
    msg_types: dict[int, type[Message]] = {
        k_EStreamControlServerHandshake: CServerHandshakeMsg,
        k_EStreamControlAuthenticationResponse: CAuthenticationResponseMsg,
        k_EStreamControlNegotiationInit: CNegotiationInitMsg,
        k_EStreamControlNegotiationSetConfig: CNegotiationSetConfigMsg,
        k_EStreamControlNegotiationComplete: CNegotiationCompleteMsg,
    }

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
        self.sent_packets = set[int]()
        self.send_packet(False, 1, self.next_pkt_id(), k_EStreamChannelDiscovery,
                         int.to_bytes(crc32c.crc32c(b'Connect'), 4, byteorder='little', signed=False))

    def next_pkt_id(self) -> int:
        for i in range(0, 65536):
            if i not in self.sent_packets:
                pkt_id = i
                break
        self.sent_packets.add(pkt_id)
        return pkt_id

    def frame_timestamp(self):
        return frame_timestamp_from_secs(time.clock_gettime(time.CLOCK_MONOTONIC))

    def send_packet(self, has_crc: bool, pkt_type: int, pkt_id: int, channel: int, payload: bytes, pad_to: int = 0):
        send_timestamp = self.frame_timestamp()
        packet = struct.pack('<1B', pkt_type | 0x80 if has_crc else pkt_type)
        packet += struct.pack('<1B', 0)  # retransmit_count
        packet += struct.pack('<1B', self.src_conn_id)
        packet += struct.pack('<1B', self.dst_conn_id)
        packet += struct.pack('<1B', channel)
        packet += struct.pack('<1h', 0)  # fragment_id
        packet += struct.pack('<1H', pkt_id)  # packet_id
        packet += struct.pack('<1I', send_timestamp)
        packet += payload
        if len(packet) < pad_to:
            packet += bytes([0xFE for _ in range(0, pad_to - len(packet))])
        if has_crc:
            packet += struct.pack('<1I', crc32c.crc32c(packet))
        self.sock.sendto(packet, self.addr)

    def send_reliable(self, channel: int, msg_type: int, message: Message):
        if channel == k_EStreamChannelControl:
            print(f'CStreamClient::SendControlMessage {msg_type}')
        if channel == k_EStreamChannelControl and frame_should_encrypt(msg_type):
            payload = frame_encrypt(message.SerializeToString(), self.auth_token, self.send_encrypt_sequence)
            self.send_encrypt_sequence += 1
        else:
            payload = message.SerializeToString()
        self.send_packet(True, 5, self.next_pkt_id(), channel,
                         int.to_bytes(msg_type, 1, byteorder='little', signed=False) + payload)

    def handle_packet(self, data: bytes):
        offset = 0
        type_and_crc, = struct.unpack_from('<B', data, offset)
        pkt_type = type_and_crc & 0x7F
        has_crc = type_and_crc & 0x80 != 0
        offset += 1
        retransmit_count, = struct.unpack_from('<1B', data, offset)
        offset += 1
        src_conn_id, = struct.unpack_from('<1B', data, offset)
        offset += 1
        dst_conn_id, = struct.unpack_from('<1B', data, offset)
        offset += 1
        channel, = struct.unpack_from('<1B', data, offset)
        offset += 1
        fragment_id, = struct.unpack_from('<1h', data, offset)
        offset += 2
        pkt_id, = struct.unpack_from('<1H', data, offset)
        offset += 2
        send_timestamp, = struct.unpack_from('<1I', data, offset)
        offset += 4
        payload = data[offset:-4] if has_crc else data[offset:]
        if has_crc:
            crc = int.from_bytes(data[-4:], byteorder='little', signed=False)
            if crc != crc32c.crc32c(data[:-4]):
                print('Bad CRC! dropping.')
                return

        if pkt_type == 0:
            self.on_unconnected(payload[0], len(data) - 4 if has_crc else len(data), payload[1:])
        elif dst_conn_id != self.src_conn_id:
            print(f'Unmatched connection ID: {dst_conn_id}! expect {self.src_conn_id}. dropping.')
            return

        if pkt_type == 2:
            self.on_connect_ack(pkt_id, src_conn_id, int.from_bytes(payload, byteorder='little', signed=False))
        elif pkt_type == 5:
            msg_type = payload[0]
            if channel == k_EStreamChannelControl and frame_should_encrypt(msg_type):
                message = frame_decrypt(payload[1:], self.auth_token, self.recv_decrypt_sequence)
                self.recv_decrypt_sequence += 1
                self.on_reliable(pkt_id, channel, msg_type, message)
            else:
                self.on_reliable(pkt_id, channel, msg_type, payload[1:])
        elif pkt_type == 7:
            self.on_ack(pkt_id, int.from_bytes(payload, byteorder='little', signed=False))
        elif pkt_type == 8:
            self.on_nack(pkt_id, int.from_bytes(payload, byteorder='little', signed=False))
        elif pkt_type == 9:
            self.on_disconnect()

    def on_unconnected(self, msg_type: int, pkt_size: int, payload: bytes):
        if msg_type != k_EStreamDiscoveryPingRequest:
            print(f'Unrecognized unconnected packet {msg_type}')
            return
        msg_size = int.from_bytes(payload[0:4], byteorder='little', signed=True)
        req: Message = CDiscoveryPingRequest()
        req.ParseFromString(payload[4:4 + msg_size])

        resp: Message = CDiscoveryPingResponse(sequence=req.sequence, packet_size_received=pkt_size)
        self.send_unconnected(k_EStreamDiscoveryPingResponse, resp.SerializeToString(), req.packet_size_requested)

    def on_ack(self, pkt_id: int, timestamp: int):
        if pkt_id not in self.sent_packets:
            return
        self.sent_packets.remove(pkt_id)

    def on_nack(self, pkt_id: int, timestamp: int):
        if pkt_id not in self.sent_packets:
            return
        self.sent_packets.remove(pkt_id)
        print(f'packet {pkt_id} returned nack')

    def on_connect_ack(self, pkt_id: int, conn_id: int, timestamp: int):
        if pkt_id not in self.sent_packets:
            return
        self.sent_packets.remove(pkt_id)
        self.dst_conn_id = conn_id
        self.connect_timestamp = timestamp
        self.send_reliable(k_EStreamChannelControl, k_EStreamControlClientHandshake,
                           CClientHandshakeMsg(info=CStreamingClientHandshakeInfo()))

    def on_reliable(self, pkt_id: int, channel: int, msg_type: int, payload: bytes):
        message = self.msg_types[msg_type]()
        try:
            message.ParseFromString(payload)
        except DecodeError as e:
            print(f'Failed to decode {payload.hex()} ({msg_type}): {e}')
            return
        self.send_ack(pkt_id, channel)
        if msg_type == k_EStreamControlServerHandshake:
            self.on_server_handshake(message)
        elif msg_type == k_EStreamControlAuthenticationResponse:
            self.on_auth_response(message)
        elif msg_type == k_EStreamControlNegotiationInit:
            self.on_negotiation_init(message)
        else:
            print(f'unhandled {msg_type}: {message}')

    def on_server_handshake(self, message: Message):
        print(f'server handshake, mtu={message.info.mtu}')
        out_msg = CAuthenticationRequestMsg(version=k_EStreamVersionCurrent, steamid=get_steamid(),
                                            token=frame_hmac256(b'Steam In-Home Streaming', self.auth_token))
        self.send_reliable(k_EStreamChannelControl, k_EStreamControlAuthenticationRequest, out_msg)

    def on_auth_response(self, message: Message):
        print(f'auth response {message}')

    def on_negotiation_init(self, message: Message):
        config = CNegotiatedConfig(reliable_data=message.reliable_data)
        for codec in message.supported_audio_codecs:
            if codec in [k_EStreamAudioCodecOpus]:
                config.selected_audio_codec = codec
        for codec in message.supported_video_codecs:
            if codec in [k_EStreamVideoCodecH264, k_EStreamVideoCodecHEVC]:
                config.selected_video_codec = codec
        config.available_video_modes.extend([CStreamVideoMode(width=1920, height=1080,
                                                              refresh_rate_numerator=5994,
                                                              refresh_rate_denominator=100)])
        config.enable_remote_hid = True
        config.enable_touch_input = True
        client_cfg = CStreamingClientConfig()
        client_cfg.maximum_resolution_x = 0
        client_cfg.maximum_resolution_y = 0
        client_cfg.enable_hardware_decoding = True
        client_cfg.enable_performance_overlay = True
        client_cfg.enable_audio_streaming = True
        client_cfg.enable_performance_icons = True
        client_cfg.enable_microphone_streaming = True
        # client_cfg.enable_video_hevc = True

        client_caps = CStreamingClientCaps()
        client_caps.system_info = "\"SystemInfo\"\n{\n\t\"OSType\"\t\t\"-197\"\n\t\"CPUID\"\t\t\"ARM\"\n\t\"CPUGhz\"\t\t\"0.000000\"\n\t\"PhysicalCPUCount\"\t\"1\"\n\t\"LogicalCPUCount\"\t\"1\"\n\t\"SystemRAM\"\t\t\"263\"\n\t\"VideoVendorID\"\t\"0\"\n\t\"VideoDeviceID\"\t\"0\"\n\t\"VideoRevision\"\t\"0\"\n\t\"VideoRAM\"\t\t\"0\"\n\t\"VideoDisplayX\"\t\"1920\"\n\t\"VideoDisplayY\"\t\"1080\"\n\t\"VideoDisplayNameID\"\t\"JN-MD133BFHDR\"\n}\n"
        client_caps.system_can_suspend = True
        client_caps.supports_video_hevc = False
        client_caps.maximum_decode_bitrate_kbps = 30000
        client_caps.maximum_burst_bitrate_kbps = 90000
        client_caps.form_factor = k_EStreamDeviceFormFactorTV

        out_msg = CNegotiationSetConfigMsg(config=config, streaming_client_config=client_cfg,
                                           streaming_client_caps=client_caps)
        self.send_reliable(k_EStreamChannelControl, k_EStreamControlNegotiationSetConfig, out_msg)

    def on_disconnect(self):
        self.closed = True

    def send_unconnected(self, msg_type: int, payload: bytes, pad_to: int):
        type_bytes = int.to_bytes(msg_type, 1, byteorder='little', signed=False)
        size_bytes = int.to_bytes(len(payload), 4, byteorder='little', signed=True)
        self.send_packet(True, 0, 0, 0, type_bytes + size_bytes + payload, pad_to)

    def send_ack(self, pkt_id: int, channel: int):
        self.send_packet(True, 7, pkt_id, channel,
                         int.to_bytes(self.frame_timestamp(), 4, byteorder='little', signed=False))
