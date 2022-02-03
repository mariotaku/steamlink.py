from base64 import b64decode

from google.protobuf.message import Message
from mbedtls import pk
import yaml

from common import get_device_id
from protobuf.steammessages_remoteclient_discovery_pb2 import CMsgRemoteDeviceAuthorizationRequest

with open('pubkey.yml') as f:
    keys = yaml.load(f)


def authorization_req_rsa_pubkey(universe) -> pk.RSA:
    if universe > 4:
        raise ValueError(f'Unsupported universe {universe}')
    rsa = pk.RSA.from_buffer(b64decode(keys[str(min(universe, 3))]))
    return rsa


def authorization_req_ticket_plain() -> Message:
    ticket = CMsgRemoteDeviceAuthorizationRequest.CKeyEscrow_Ticket()
    ticket.password = '1234'
    ticket.identifier = get_device_id()
    raise NotImplementedError()


def authorization_req(token: str, name: str) -> Message:
    rsa = authorization_req_rsa_pubkey(1)
    plain = authorization_req_ticket_plain()
    encrypted_request = rsa.encrypt(plain.SerializeToString())
    return CMsgRemoteDeviceAuthorizationRequest(device_token=token, device_name=name,
                                                encrypted_request=encrypted_request)
