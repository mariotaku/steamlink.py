import os.path
import struct
from asyncio import DatagramTransport
from os import path

import asyncio
import secrets
from google.protobuf.message import Message

from protobuf.steammessages_remoteclient_discovery_pb2 import CMsgRemoteClientBroadcastHeader, \
    CMsgRemoteClientBroadcastDiscovery, k_ERemoteClientBroadcastMsgDiscovery, CMsgRemoteClientBroadcastStatus, \
    k_ERemoteClientBroadcastMsgStatus, CMsgRemoteDeviceAuthorizationResponse, k_ERemoteDeviceAuthorizationResponse, \
    k_ERemoteDeviceAuthorizationRequest, CMsgRemoteDeviceAuthorizationRequest, k_ERemoteDeviceProofRequest, \
    CMsgRemoteDeviceProofRequest, CMsgRemoteDeviceStreamingResponse, k_ERemoteDeviceStreamingResponse
from service import ccrypto

pkt_magic: bytes = bytes([0xff, 0xff, 0xff, 0xff, 0x21, 0x4c, 0x5f, 0xa0])

pkt_types: dict[int, type[Message]] = {
    k_ERemoteClientBroadcastMsgDiscovery: CMsgRemoteClientBroadcastDiscovery,
    k_ERemoteClientBroadcastMsgStatus: CMsgRemoteClientBroadcastStatus,
    k_ERemoteDeviceAuthorizationRequest: CMsgRemoteDeviceAuthorizationRequest,
    k_ERemoteDeviceAuthorizationResponse: CMsgRemoteDeviceAuthorizationResponse,
    k_ERemoteDeviceStreamingResponse: CMsgRemoteDeviceStreamingResponse,
    k_ERemoteDeviceProofRequest: CMsgRemoteDeviceProofRequest,
}


def _load_bytes(file: str, size: int) -> bytes:
    with open(file) as f:
        s = f.read(size * 2)
        if len(s) == size * 2:
            return bytes.fromhex(s)
    raise IOError('Bytes not valid')


def _obtain_random_bytes(file: str, size: int) -> bytes:
    try:
        return _load_bytes(file, size)
    except IOError:
        pass
    value = secrets.token_bytes(size)
    return _save_bytes(file, value)


def _save_bytes(file, value):
    filedir = os.path.dirname(file)
    if not os.path.exists(filedir):
        os.makedirs(filedir, exist_ok=True)
    with open(file, 'w') as f:
        f.write(value.hex())
        f.flush()
    return value


def _config_path(name: str) -> str:
    return path.join(path.expanduser('~'), '.steamlink', name)


def get_device_id() -> int:
    return int.from_bytes(_obtain_random_bytes(_config_path('device_id.txt'), 8), byteorder='big', signed=False)


def get_secret_key() -> bytes:
    return _obtain_random_bytes(_config_path('secret_key.txt'), 32)


def get_steamid() -> int:
    return int.from_bytes(_load_bytes(_config_path('steamid.txt'), 8), byteorder='big', signed=False)


def set_steamid(steamid: int):
    return _save_bytes(_config_path('steamid.txt'), steamid.to_bytes(8, byteorder='big', signed=False))


def message_parse(data: bytes) -> tuple[Message, Message]:
    mlen = len(data)
    if mlen < 20:
        raise ValueError('Invalid packet: too short')
    offset = 0
    magic, = struct.unpack_from('<8s', data, offset)
    if magic != pkt_magic:
        raise ValueError(f'Invalid packet: wrong magic {magic.hex()}')
    offset += 8
    header_len, = struct.unpack_from('<1I', data, offset)
    offset += 4
    if mlen < offset + header_len:
        raise ValueError('Message too short')
    header = CMsgRemoteClientBroadcastHeader()
    header.ParseFromString(data[offset:offset + header_len])
    offset += header_len
    body_len, = struct.unpack_from('<1I', data, offset)
    offset += 4
    body = pkt_types[header.msg_type]()
    body.ParseFromString(data[offset:offset + body_len])
    return header, body


def message_serialize(msg_type: int, body: Message) -> bytes:
    header = CMsgRemoteClientBroadcastHeader(client_id=get_device_id(), msg_type=msg_type)
    header_bytes = header.SerializeToString()
    body_bytes = body.SerializeToString()
    result = bytes(pkt_magic)
    result += struct.pack('<1I', len(header_bytes))
    result += header_bytes
    result += struct.pack('<1I', len(body_bytes))
    result += body_bytes
    return result


def device_token(dev_id: int, enc_key: bytes) -> bytes:
    return ccrypto.symmetric_encrypt(dev_id.to_bytes(8, byteorder='little', signed=False), enc_key)


class ServiceProtocol(asyncio.DatagramProtocol):
    transport: DatagramTransport

    def __init__(self):
        super().__init__()

    def connection_made(self, transport: DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        header, message = message_parse(data)
        self.message_received(header, message, addr)

    def send_message(self, msg_type: int, msg: Message, addr: tuple[str, int]):
        data = message_serialize(msg_type, msg)
        self.transport.sendto(data, addr)

    def message_received(self, header: Message, msg: Message, addr: tuple[str, int]):
        pass
