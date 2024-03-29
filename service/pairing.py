import os.path
from base64 import b64decode

import yaml
from google.protobuf.message import Message

from protobuf.steammessages_remoteclient_discovery_pb2 import CMsgRemoteDeviceAuthorizationRequest
from service import ccrypto
from service.common import get_device_id, device_token

with open(os.path.join(os.path.dirname(__file__), 'pubkey.yml')) as f:
    keys = yaml.load(f, Loader=yaml.FullLoader)


def authorization_req_rsa_pubkey(universe: int) -> bytes:
    if universe > 4:
        raise ValueError(f'Unsupported universe {universe}')
    return b64decode(keys[min(universe, 3)])


def authorization_req_ticket_plain(dev_id: int, pin: str, enc_key: bytes, name: str) -> Message:
    ticket = CMsgRemoteDeviceAuthorizationRequest.CKeyEscrow_Ticket()
    ticket.password = pin.encode('utf-8')
    ticket.identifier = dev_id
    ticket.payload = enc_key
    ticket.usage = 0  # k_EKeyEscrowUsageStreamingDevice
    ticket.device_name = name
    ticket.device_model = '1234'
    ticket.device_serial = 'A1B2C3D4E5'
    ticket.device_provisioning_id = 123456
    return ticket


def authorization_req(universe: int, device_name: str, enc_key: bytes, pin: str) -> Message:
    pubkey = authorization_req_rsa_pubkey(universe)
    device_id = get_device_id()
    plain = authorization_req_ticket_plain(device_id, pin, enc_key, device_name)
    encrypted_request = ccrypto.rsa_encrypt(plain.SerializeToString(), pubkey)
    return CMsgRemoteDeviceAuthorizationRequest(device_token=device_token(device_id, enc_key), device_name=device_name,
                                                encrypted_request=encrypted_request)
