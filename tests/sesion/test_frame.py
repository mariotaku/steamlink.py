from unittest import TestCase

import secrets

from session.frame import frame_encrypt, frame_decrypt


class FrameTest(TestCase):
    def test_frame_encrypt(self):
        plain = secrets.token_bytes(20)
        key = secrets.token_bytes(16)
        encrypted = frame_encrypt(plain, key, 0)
        frame_decrypt(encrypted, key, 0)
