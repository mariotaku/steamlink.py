import os.path

import secrets


def _obtain_random_bytes(file: str, size: int) -> bytes:
    try:
        with open(file) as f:
            s = f.read(size * 2)
            if len(s) == size * 2:
                print(s)
                return bytes.fromhex(s)
    except IOError:
        pass
    value = secrets.token_bytes(size)
    filedir = os.path.dirname(file)
    if not os.path.exists(filedir):
        os.makedirs(filedir, exist_ok=True)
    with open(file, 'w') as f:
        f.write(value.hex())
        f.flush()
    return value


def get_device_id() -> int:
    return int.from_bytes(_obtain_random_bytes('../.client/device_id.txt', 8), byteorder='big', signed=False)


def get_secret_key() -> bytes:
    return _obtain_random_bytes('.client/secret_key.txt', 32)
