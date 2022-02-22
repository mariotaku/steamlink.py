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
from alsaaudio import PCM as AlsaPCM, PCM_PLAYBACK, PCM_FORMAT_S16_LE, PCM_NORMAL
from google.protobuf.message import Message, DecodeError
from opuslib import Decoder as OpusDecoder
from typing import Optional

from protobuf.steammessages_remoteclient_discovery_pb2 import EStreamTransport, k_EStreamDeviceFormFactorTV
from protobuf.steammessages_remoteplay_pb2 import k_EStreamChannelDiscovery, k_EStreamChannelControl, \
    k_EStreamControlAuthenticationResponse, CAuthenticationResponseMsg, CNegotiationInitMsg, \
    k_EStreamControlNegotiationInit, CNegotiationSetConfigMsg, k_EStreamControlNegotiationSetConfig, \
    k_EStreamControlNegotiationComplete, CNegotiationCompleteMsg, k_EStreamControlAuthenticationRequest, \
    CAuthenticationRequestMsg, k_EStreamControlClientHandshake, CClientHandshakeMsg, CStreamingClientHandshakeInfo, \
    k_EStreamControlServerHandshake, k_EStreamDiscoveryPingRequest, \
    CDiscoveryPingRequest, CDiscoveryPingResponse, k_EStreamDiscoveryPingResponse, CServerHandshakeMsg, \
    CNegotiatedConfig, CStreamVideoMode, CStreamingClientConfig, CStreamingClientCaps, k_EStreamAudioCodecOpus, \
    k_EStreamVideoCodecH264, k_EStreamVideoCodecHEVC, k_EStreamVersionCurrent, CSetQoSMsg, k_EStreamControlSetQoS, \
    CSetTargetBitrateMsg, k_EStreamControlSetTargetBitrate, EStreamControlMessage, k_EStreamControlStartAudioData, \
    CStartAudioDataMsg, k_EStreamControlStartVideoData, k_EStreamControlStopAudioData, CStopAudioDataMsg, \
    CStartVideoDataMsg, CStopVideoDataMsg, k_EStreamControlStopVideoData, k_EStreamControlSetSpectatorMode, \
    CSetSpectatorModeMsg, CSetTitleMsg, k_EStreamControlSetTitle, CSetIconMsg, k_EStreamControlSetIcon, \
    k_EStreamControlSetCursor, CSetCursorMsg, CShowCursorMsg, k_EStreamControlShowCursor, CHideCursorMsg, \
    k_EStreamControlHideCursor, CGetCursorImageMsg, k_EStreamControlGetCursorImage, CSetCursorImageMsg, \
    k_EStreamControlSetCursorImage, CDeleteCursorMsg, k_EStreamControlDeleteCursor, k_EStreamControlSetTargetFramerate, \
    CSetTargetFramerateMsg, CSetKeymapMsg, k_EStreamControlSetKeymap, CSetActivityMsg, k_EStreamControlSetActivity, \
    k_EStreamControlSetCaptureSize, CSetCaptureSizeMsg, k_EStreamControlVideoEncoderInfo, CVideoEncoderInfoMsg, \
    k_EStreamDataPacket
from service.common import get_steamid
from session.frame import frame_should_encrypt, frame_encrypt, frame_decrypt, frame_hmac256, frame_timestamp_from_secs, \
    FrameAssembler, Frame, DataFrameHeader, FRAME_HEADER_LENGTH
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
    msg_types: dict[int, type(Message)] = {
        k_EStreamControlServerHandshake: CServerHandshakeMsg,
        k_EStreamControlAuthenticationResponse: CAuthenticationResponseMsg,
        k_EStreamControlNegotiationInit: CNegotiationInitMsg,
        k_EStreamControlNegotiationSetConfig: CNegotiationSetConfigMsg,
        k_EStreamControlNegotiationComplete: CNegotiationCompleteMsg,
        k_EStreamControlSetQoS: CSetQoSMsg,
        k_EStreamControlSetTargetBitrate: CSetTargetBitrateMsg,
        k_EStreamControlSetTargetFramerate: CSetTargetFramerateMsg,
        k_EStreamControlSetTitle: CSetTitleMsg,
        k_EStreamControlSetIcon: CSetIconMsg,
        k_EStreamControlShowCursor: CShowCursorMsg,
        k_EStreamControlHideCursor: CHideCursorMsg,
        k_EStreamControlSetCursor: CSetCursorMsg,
        k_EStreamControlGetCursorImage: CGetCursorImageMsg,
        k_EStreamControlSetCursorImage: CSetCursorImageMsg,
        k_EStreamControlDeleteCursor: CDeleteCursorMsg,
        k_EStreamControlStartAudioData: CStartAudioDataMsg,
        k_EStreamControlStopAudioData: CStopAudioDataMsg,
        k_EStreamControlStartVideoData: CStartVideoDataMsg,
        k_EStreamControlStopVideoData: CStopVideoDataMsg,
        k_EStreamControlSetSpectatorMode: CSetSpectatorModeMsg,
        k_EStreamControlSetKeymap: CSetKeymapMsg,
        k_EStreamControlSetActivity: CSetActivityMsg,
        k_EStreamControlSetCaptureSize: CSetCaptureSizeMsg,
        k_EStreamControlVideoEncoderInfo: CVideoEncoderInfoMsg,
    }
    audio_channel: CStartAudioDataMsg = None
    video_channel: CStopVideoDataMsg = None

    audio_decoder: OpusDecoder = None
    audio_sink: AlsaPCM = None

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
        self.frame_assembler = FrameAssembler()
        self._next_pkt_id = 0
        self.audio_executor = ThreadPoolExecutor(max_workers=1)
        self.send_packet(False, PacketType.CONNECT, self.next_pkt_id(), k_EStreamChannelDiscovery,
                         int.to_bytes(crc32c.crc32c(b'Connect'), 4, byteorder='little', signed=False))

    def next_pkt_id(self) -> int:
        pkt_id = 0
        for i in range(self._next_pkt_id, 65536):
            if i not in self.sent_packets:
                pkt_id = i
                break
        self.sent_packets.add(pkt_id)
        return pkt_id

    def frame_timestamp(self):
        return frame_timestamp_from_secs(time.clock_gettime(time.CLOCK_MONOTONIC))

    def send_packet(self, has_crc: bool, pkt_type: PacketType, pkt_id: int, channel: int, payload: bytes = b'',
                    pad_to: int = 0):
        send_timestamp = self.frame_timestamp()
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

    def send_reliable(self, channel: int, msg_type: int, message: Message):
        if channel == k_EStreamChannelControl:
            # print(f'CStreamClient::SendControlMessage {msg_type}')
            pass
        if channel == k_EStreamChannelControl and frame_should_encrypt(msg_type):
            payload = frame_encrypt(message.SerializeToString(), self.auth_token, self.send_encrypt_sequence)
            self.send_encrypt_sequence += 1
        else:
            payload = message.SerializeToString()
        self.send_packet(True, PacketType.RELIABLE, self.next_pkt_id(), channel,
                         int.to_bytes(msg_type, 1, byteorder='little', signed=False) + payload)

    def handle_packet(self, data: bytes):
        packet = Packet.parse(data)
        header = packet.header
        payload = packet.body
        if header.has_crc and not packet.crc_ok:
            print('Bad CRC! dropping.')
            return

        if header.pkt_type == PacketType.UNCONNECTED:
            self.on_unconnected(payload[0], len(data) - 4 if header.has_crc else len(data), payload[1:])
            return
        elif header.dst_conn_id != self.src_conn_id:
            print(f'Unmatched connection ID: {header.dst_conn_id}! expect {self.src_conn_id}. dropping.')
            return
        elif header.pkt_type == PacketType.DISCONNECT:
            self.on_disconnect()
            return

        if self.frame_assembler.add_packet(packet):
            if packet.header.pkt_type in [PacketType.RELIABLE, PacketType.RELIABLE_FRAG]:
                self.send_ack(packet.header.pkt_id, packet.header.channel)
        else:
            # print(f'Send NACK to {packet.header.pkt_type}')
            if packet.header.pkt_type in [PacketType.RELIABLE, PacketType.RELIABLE_FRAG]:
                self.send_nack(packet.header.pkt_id, packet.header.channel)

        while True:
            frame = self.frame_assembler.poll_frame()
            if not frame:
                break
            self.handle_frame(frame)

    def handle_frame(self, frame: Frame):
        header = frame.header
        payload = frame.body

        if header.pkt_type == PacketType.CONNECT_ACK:
            self.on_connect_ack(header.pkt_id, header.src_conn_id,
                                int.from_bytes(payload, byteorder='little', signed=False))
        elif header.pkt_type == PacketType.RELIABLE:
            msg_type = payload[0]
            if header.channel == k_EStreamChannelControl and frame_should_encrypt(msg_type):
                try:
                    message = frame_decrypt(payload[1:], self.auth_token, self.recv_decrypt_sequence)
                except ValueError as e:
                    raise ValueError(
                        f'Failed to decode message (head {header}) {EStreamControlMessage.Name(msg_type)}: {e}')
                self.recv_decrypt_sequence += 1
                self.on_reliable(header.pkt_id, header.channel, msg_type, message)
            else:
                self.on_reliable(header.pkt_id, header.channel, msg_type, payload[1:])
        elif header.pkt_type == PacketType.UNRELIABLE:
            self.on_unreliable(header.pkt_id, header.channel, payload[0], payload[1:])
        elif header.pkt_type == PacketType.ACK:
            self.on_ack(header.pkt_id, int.from_bytes(payload, byteorder='little', signed=False))
        elif header.pkt_type == PacketType.NACK:
            self.on_nack(header.pkt_id, int.from_bytes(payload, byteorder='little', signed=False))

    def on_unconnected(self, msg_type: int, pkt_size: int, payload: bytes):
        if msg_type != k_EStreamDiscoveryPingRequest:
            print(f'Unrecognized unconnected packet {msg_type}')
            return
        msg_size = int.from_bytes(payload[0:4], byteorder='little', signed=True)
        req: CDiscoveryPingRequest = CDiscoveryPingRequest()
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
        msg_ctor = self.msg_types.get(msg_type, None)
        if not msg_ctor:
            print(f'Unrecognized type {EStreamControlMessage.Name(msg_type)}')
            return
        message = msg_ctor()
        try:
            message.ParseFromString(payload)
        except DecodeError as e:
            print(f'Failed to decode {payload.hex()} ({msg_type}): {e}')
            return
        if msg_type == k_EStreamControlServerHandshake:
            self.on_server_handshake(message)
        elif msg_type == k_EStreamControlAuthenticationResponse:
            self.on_auth_response(message)
        elif msg_type == k_EStreamControlNegotiationInit:
            self.on_negotiation_init(pkt_id, message)
        elif msg_type == k_EStreamControlNegotiationSetConfig:
            self.on_negotation_set_config(pkt_id, message)
        elif msg_type == k_EStreamControlShowCursor:
            # Move cursor location
            pass
        elif msg_type == k_EStreamControlSetIcon:
            # Set app icon
            pass
        elif msg_type == k_EStreamControlSetKeymap:
            # Set keymap
            pass
        elif msg_type == k_EStreamControlSetCursor:
            # Set keymap
            pass
        elif msg_type == k_EStreamControlVideoEncoderInfo:
            # Video encoder info (for display)
            pass
        elif msg_type == k_EStreamControlStartAudioData:
            self.frame_assembler.enable_channel(message.channel)
            self.audio_channel = message
            self.audio_decoder = OpusDecoder(message.frequency, message.channels)
            self.audio_sink = AlsaPCM(type=PCM_PLAYBACK, mode=PCM_NORMAL, rate=message.frequency,
                                      channels=message.channels, format=PCM_FORMAT_S16_LE, periodsize=32,
                                      device='default')
            print(f'start audio data {message}')
        elif msg_type == k_EStreamControlStartVideoData:
            self.frame_assembler.enable_channel(message.channel)
            self.video_channel = message
        elif msg_type == k_EStreamControlStopAudioData:
            if self.audio_channel:
                self.frame_assembler.enable_channel(self.audio_channel.channel, enabled=False)
            self.audio_channel = None
        elif msg_type == k_EStreamControlStopVideoData:
            if self.video_channel:
                self.frame_assembler.enable_channel(self.video_channel.channel, enabled=False)
            self.video_channel = None
        elif msg_type == k_EStreamControlSetTitle:
            print(f'Set title {message.text}')
        else:
            print(f'unhandled {EStreamControlMessage.Name(msg_type)}: {message}')
            pass

    def on_unreliable(self, pkt_id: int, channel: int, msg_type: int, payload: bytes):
        if msg_type != k_EStreamDataPacket:
            return
        header: Optional[DataFrameHeader] = None
        if len(payload) > FRAME_HEADER_LENGTH:
            header = DataFrameHeader.parse(payload)
            payload = payload[FRAME_HEADER_LENGTH:]
        if self.audio_channel and self.audio_channel.channel == channel:
            self.on_audio_data(header, payload)
        elif self.video_channel and self.video_channel.channel == channel:
            self.on_video_data(header, payload)

    def on_audio_data(self, header: Optional[DataFrameHeader], payload: bytes):
        if not self.audio_decoder:
            return
        self.audio_executor.submit(lambda: self.audio_sink.write(self.audio_decoder.decode(payload, 480)))

    def on_video_data(self, header: Optional[DataFrameHeader], payload: bytes):
        sequence, flags, num2, num3 = struct.unpack('<HBHH', payload[:7])
        protected = flags & 0x10
        encrypted = flags & 0x20

    def on_server_handshake(self, message: CServerHandshakeMsg):
        out_msg = CAuthenticationRequestMsg(version=k_EStreamVersionCurrent, steamid=get_steamid(),
                                            token=frame_hmac256(b'Steam In-Home Streaming', self.auth_token))
        self.send_reliable(k_EStreamChannelControl, k_EStreamControlAuthenticationRequest, out_msg)

    def on_auth_response(self, message: CAuthenticationResponseMsg):
        if message.result != 0:
            self.closed = True

    def on_negotiation_init(self, pkt_id: int, message: CNegotiationInitMsg):
        config = CNegotiatedConfig(reliable_data=message.reliable_data)
        for codec in message.supported_audio_codecs:
            if codec in [k_EStreamAudioCodecOpus]:
                config.selected_audio_codec = codec
        for codec in message.supported_video_codecs:
            supported_codecs = [k_EStreamVideoCodecH264, k_EStreamVideoCodecHEVC]
            if codec in supported_codecs:
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
        client_caps.system_can_suspend = True
        # client_caps.supports_video_hevc = True
        client_caps.maximum_decode_bitrate_kbps = 30000
        client_caps.maximum_burst_bitrate_kbps = 90000
        client_caps.form_factor = k_EStreamDeviceFormFactorTV

        out_msg = CNegotiationSetConfigMsg(config=config, streaming_client_config=client_cfg,
                                           streaming_client_caps=client_caps)
        self._next_pkt_id = pkt_id
        self.send_reliable(k_EStreamChannelControl, k_EStreamControlNegotiationSetConfig, out_msg)

    def on_negotation_set_config(self, pkt_id: int, message: Message):
        self._next_pkt_id = pkt_id
        out_msg = CNegotiationCompleteMsg()
        self.send_reliable(k_EStreamChannelControl, k_EStreamControlNegotiationComplete, out_msg)

    def on_disconnect(self):
        self.closed = True

    def hangup(self):
        self.send_packet(True, PacketType.DISCONNECT, self.next_pkt_id(), k_EStreamChannelDiscovery)

    def send_unconnected(self, msg_type: int, payload: bytes, pad_to: int):
        type_bytes = int.to_bytes(msg_type, 1, byteorder='little', signed=False)
        size_bytes = int.to_bytes(len(payload), 4, byteorder='little', signed=True)
        self.send_packet(True, PacketType.UNCONNECTED, 0, 0, type_bytes + size_bytes + payload, pad_to)

    def send_ack(self, pkt_id: int, channel: int):
        self.send_packet(True, PacketType.ACK, pkt_id, channel,
                         int.to_bytes(self.frame_timestamp(), 4, byteorder='little', signed=False))

    def send_nack(self, pkt_id: int, channel: int):
        self.send_packet(True, PacketType.NACK, pkt_id, channel,
                         int.to_bytes(self.frame_timestamp(), 4, byteorder='little', signed=False))
