from Crypto.Hash import HMAC, MD5

from protobuf.steammessages_remoteplay_pb2 import k_EStreamControlAuthenticationResponse, \
    k_EStreamControlAuthenticationRequest
from service import ccrypto


def frame_should_encrypt(msg_type: int) -> bool:
    return msg_type not in [k_EStreamControlAuthenticationRequest, k_EStreamControlAuthenticationResponse]


def frame_encrypt(data: bytes, key: bytes) -> bytes:
    iv = HMAC.new(key, data, MD5).digest()
    return iv + ccrypto.symmetric_encrypt_with_iv(data, iv, key, False)


def frame_decrypt(encrypted: bytes, key: bytes) -> bytes:
    iv = encrypted[0:16]
    plain = ccrypto.symmetric_decrypt_with_iv(encrypted[16:], iv, key)
    HMAC.new(key, plain, MD5).verify(iv)
    return plain
