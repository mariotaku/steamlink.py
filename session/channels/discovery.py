from protobuf.steammessages_remoteplay_pb2 import k_EStreamDiscoveryPingRequest, CDiscoveryPingRequest, \
    CDiscoveryPingResponse, k_EStreamDiscoveryPingResponse
from session.channels.base import Channel
from session.packet import Packet, PacketType


class Discovery(Channel):
    def handle_packet(self, packet: Packet):
        header = packet.header
        payload = packet.body
        if header.pkt_type == PacketType.UNCONNECTED:
            self.on_unconnected(payload[0], packet.size, payload[1:])

    def on_unconnected(self, msg_type: int, pkt_size: int, payload: bytes):
        if msg_type != k_EStreamDiscoveryPingRequest:
            print(f'Unrecognized unconnected packet {msg_type}')
            return
        msg_size = int.from_bytes(payload[0:4], byteorder='little', signed=True)
        req: CDiscoveryPingRequest = CDiscoveryPingRequest()
        req.ParseFromString(payload[4:4 + msg_size])

        resp = CDiscoveryPingResponse(sequence=req.sequence, packet_size_received=pkt_size)
        self.send_unconnected(k_EStreamDiscoveryPingResponse, resp.SerializeToString(), req.packet_size_requested)
