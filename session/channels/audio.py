from concurrent.futures import ThreadPoolExecutor

from alsaaudio import PCM, PCM_PLAYBACK, PCM_NORMAL, PCM_FORMAT_S16_LE
from opuslib import Decoder as OpusDecoder
from typing import Optional

from protobuf.steammessages_remoteplay_pb2 import CStartAudioDataMsg
from session.channels.data import Data
from session.client import Client
from session.frame import DataFrameHeader


class Audio(Data):
    decoder: OpusDecoder
    sink: PCM

    def __init__(self, client: Client, message: CStartAudioDataMsg):
        super().__init__(client, message.channel)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.decoder = OpusDecoder(message.frequency, message.channels)
        self.sink = PCM(type=PCM_PLAYBACK, mode=PCM_NORMAL, rate=message.frequency,
                        channels=message.channels, format=PCM_FORMAT_S16_LE, periodsize=32,
                        device='default')

    def handle_data(self, header: Optional[DataFrameHeader], payload: bytes):
        self.executor.submit(lambda: self.sink.write(self.decoder.decode(payload, 480)))
