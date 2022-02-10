from Crypto.Hash import HMAC, MD5, SHA256

from protobuf.steammessages_remoteplay_pb2 import k_EStreamControlAuthenticationResponse, \
    k_EStreamControlAuthenticationRequest, k_EStreamControlServerHandshake, k_EStreamControlClientHandshake
from service import ccrypto


def frame_should_encrypt(msg_type: int) -> bool:
    return msg_type not in [k_EStreamControlClientHandshake, k_EStreamControlServerHandshake,
                            k_EStreamControlAuthenticationRequest, k_EStreamControlAuthenticationResponse]


def frame_encrypt(data: bytes, key: bytes, sequence: int) -> bytes:
    plain = int.to_bytes(sequence, 8, byteorder='little', signed=False) + data
    iv = HMAC.new(key, plain, MD5).digest()
    return iv + ccrypto.symmetric_encrypt_with_iv(plain, iv, key, False)


def frame_decrypt(encrypted: bytes, key: bytes, expect_sequence: int) -> bytes:
    iv = encrypted[0:16]
    plain = ccrypto.symmetric_decrypt_with_iv(encrypted[16:], iv, key)
    HMAC.new(key, plain, MD5).verify(iv)
    if expect_sequence >= 0:
        actual_sequence = int.from_bytes(plain[:8], byteorder='little', signed=False)
        if expect_sequence != actual_sequence:
            raise ValueError(f'Expected sequence {expect_sequence}, actual {actual_sequence}')
    return plain[8:]


def frame_hmac256(data: bytes, key: bytes) -> bytes:
    return HMAC.new(key, data, SHA256).digest()


def frame_timestamp_from_secs(timestamp: float) -> int:
    return int(timestamp * 65536) & 0xFFFFFFFF
