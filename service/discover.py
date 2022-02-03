import socket
import threading
import struct

from google.protobuf.message import Message, DecodeError
from typing import Callable, Type

from common import get_device_id
from protobuf.steammessages_remoteclient_discovery_pb2 import CMsgRemoteClientBroadcastHeader, \
    k_ERemoteClientBroadcastMsgDiscovery, CMsgRemoteClientBroadcastStatus, CMsgRemoteClientBroadcastDiscovery, \
    k_ERemoteClientBroadcastMsgStatus

pkg_magic = bytes([0xff, 0xff, 0xff, 0xff, 0x21, 0x4c, 0x5f, 0xa0])


def parse_broadcast_message(data: bytes, factory: Callable[[int], Type[Message]]):
    mlen = len(data)
    if mlen < 20:
        raise ValueError('Invalid packet: too short')
    offset = 0
    magic, = struct.unpack_from('<8s', data, offset)
    if magic != pkg_magic:
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
    body = factory(header.msg_type)()
    body.ParseFromString(data[offset:offset + body_len])
    return header, body


def serialize_broadcast_message(msg_type: int, body: Message):
    header = CMsgRemoteClientBroadcastHeader(client_id=get_device_id(), msg_type=msg_type)
    header_bytes = header.SerializeToString()
    body_bytes = body.SerializeToString()
    result = bytes(pkg_magic)
    result += struct.pack('<1I', len(header_bytes))
    result += header_bytes
    result += struct.pack('<1I', len(body_bytes))
    result += body_bytes
    return result


def broadcast_msg_type(t: int):
    if t == k_ERemoteClientBroadcastMsgDiscovery:
        return CMsgRemoteClientBroadcastDiscovery
    elif t == k_ERemoteClientBroadcastMsgStatus:
        return CMsgRemoteClientBroadcastStatus
    else:
        raise ValueError(f'Unsupported type {t}')


class ListenerThread(threading.Thread):
    def run(self):
        sock = socket.socket(socket.AF_INET, type=socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', 27036))
        while True:
            try:
                data, (ip, port) = sock.recvfrom(2048)
                try:
                    header, body = parse_broadcast_message(data, broadcast_msg_type)
                except DecodeError as e:
                    print(e)
                    continue
                except ValueError as e:
                    print(e)
                    continue
                if ip == '127.0.0.1':
                    continue
                if header.msg_type != k_ERemoteClientBroadcastMsgStatus:
                    continue
                print(f'Received host status from {ip}:{port}')
                print(header)
                print(body)

            except KeyboardInterrupt:
                break


def broadcast_discovery():
    seq_num = 0
    body = CMsgRemoteClientBroadcastDiscovery(seq_num=seq_num)
    message = serialize_broadcast_message(k_ERemoteClientBroadcastMsgDiscovery, body)
    seq_num += 1

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)  # UDP
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.sendto(message, ('255.255.255.255', 27036))

    while True:
        try:
            data, (ip, port) = sock.recvfrom(2048)
            try:
                header, body = parse_broadcast_message(data, broadcast_msg_type)
            except DecodeError as e:
                print(e)
                continue
            except ValueError as e:
                print(e)
                continue
            if header.msg_type != k_ERemoteClientBroadcastMsgStatus:
                continue
            print(f'Received host status from {ip}:{port}')
            print(header)
            print(body)

        except KeyboardInterrupt:
            break
    sock.close()


if __name__ == '__main__':
    broadcast_discovery()
