# Algorithm described as per https://pkg.go.dev/github.com/Tommy-42/go-steam/cryptoutil
import secrets
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto.Hash import SHA1
from Crypto.PublicKey import RSA


def rsa_encrypt(plaintext: bytes, pubkey: bytes) -> bytes:
    rsa_key = RSA.import_key(pubkey)
    cipher = PKCS1_OAEP.new(rsa_key, hashAlgo=SHA1)
    return cipher.encrypt(plaintext)


def symmetric_encrypt_with_iv(plaintext: bytes, iv: bytes, key: bytes, with_iv: bool) -> bytes:
    def pkcs7padding(data: bytes, block_size: int = 16) -> bytes:
        if type(data) != bytearray and type(data) != bytes:
            raise TypeError("Only support bytearray/bytes !")
        pl = block_size - (len(data) % block_size)
        return data + bytearray([pl for i in range(pl)])

    # AES-CBC-PKCS7Padding
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pkcs7padding(plaintext))
    if with_iv:
        # AES-ECB
        iv_cipher = AES.new(key, AES.MODE_ECB)
        return iv_cipher.encrypt(iv) + encrypted
    return encrypted


def symmetric_decrypt(encrypted: bytes, key: bytes) -> bytes:
    iv_cipher = AES.new(key, AES.MODE_ECB)
    iv = iv_cipher.decrypt(encrypted[0:16])
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.decrypt(encrypted[16:])


def symmetric_encrypt(plaintext: bytes, key: bytes) -> bytes:
    return symmetric_encrypt_with_iv(plaintext, secrets.token_bytes(16), key, True)
