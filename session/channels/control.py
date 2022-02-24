from google.protobuf.message import DecodeError, Message

from protobuf.steammessages_remoteclient_discovery_pb2 import k_EStreamDeviceFormFactorTV
from protobuf.steammessages_remoteplay_pb2 import k_EStreamControlClientHandshake, k_EStreamControlServerHandshake, \
    k_EStreamControlAuthenticationResponse, k_EStreamControlAuthenticationRequest, EStreamControlMessage, \
    k_EStreamControlSetTitle, k_EStreamControlStopVideoData, k_EStreamControlStopAudioData, \
    k_EStreamControlStartVideoData, k_EStreamControlStartAudioData, k_EStreamControlVideoEncoderInfo, \
    k_EStreamControlSetCursor, k_EStreamControlSetKeymap, k_EStreamControlSetIcon, k_EStreamControlShowCursor, \
    k_EStreamControlNegotiationSetConfig, k_EStreamControlNegotiationInit, CVideoEncoderInfoMsg, CSetCaptureSizeMsg, \
    k_EStreamControlSetCaptureSize, CSetActivityMsg, k_EStreamControlSetActivity, CSetKeymapMsg, CSetSpectatorModeMsg, \
    k_EStreamControlSetSpectatorMode, CStopVideoDataMsg, CStartVideoDataMsg, CStopAudioDataMsg, CStartAudioDataMsg, \
    CDeleteCursorMsg, k_EStreamControlDeleteCursor, CSetCursorImageMsg, k_EStreamControlSetCursorImage, \
    CGetCursorImageMsg, k_EStreamControlGetCursorImage, CSetCursorMsg, CHideCursorMsg, k_EStreamControlHideCursor, \
    CShowCursorMsg, CSetIconMsg, CSetTitleMsg, CSetTargetFramerateMsg, k_EStreamControlSetTargetFramerate, \
    CSetTargetBitrateMsg, k_EStreamControlSetTargetBitrate, CSetQoSMsg, k_EStreamControlSetQoS, CNegotiationCompleteMsg, \
    k_EStreamControlNegotiationComplete, CNegotiationSetConfigMsg, CNegotiationInitMsg, CAuthenticationResponseMsg, \
    CServerHandshakeMsg, k_EStreamVersionCurrent, CAuthenticationRequestMsg, \
    CStreamingClientCaps, CStreamingClientConfig, CStreamVideoMode, k_EStreamVideoCodecHEVC, k_EStreamVideoCodecH264, \
    k_EStreamAudioCodecOpus, CNegotiatedConfig
from service.common import get_steamid
from session.channels.audio import Audio
from session.channels.base import Channel
from session.channels.video import Video
from session.frame import Frame, frame_should_encrypt, frame_decrypt, frame_hmac256, frame_encrypt
from session.packet import PacketType


class Control(Channel):
    msg_types: dict[int, type(Message)] = {
        k_EStreamControlServerHandshake: CServerHandshakeMsg,
        k_EStreamControlAuthenticationResponse: CAuthenticationResponseMsg,
        k_EStreamControlNegotiationInit: CNegotiationInitMsg,
        k_EStreamControlNegotiationSetConfig: CNegotiationSetConfigMsg,
        k_EStreamControlNegotiationComplete: CNegotiationCompleteMsg,
        k_EStreamControlSetQoS: CSetQoSMsg,
        k_EStreamControlSetTargetBitrate: CSetTargetBitrateMsg,
        k_EStreamControlSetTargetFramerate: CSetTargetFramerateMsg,
        k_EStreamControlSetTitle: CSetTitleMsg,
        k_EStreamControlSetIcon: CSetIconMsg,
        k_EStreamControlShowCursor: CShowCursorMsg,
        k_EStreamControlHideCursor: CHideCursorMsg,
        k_EStreamControlSetCursor: CSetCursorMsg,
        k_EStreamControlGetCursorImage: CGetCursorImageMsg,
        k_EStreamControlSetCursorImage: CSetCursorImageMsg,
        k_EStreamControlDeleteCursor: CDeleteCursorMsg,
        k_EStreamControlStartAudioData: CStartAudioDataMsg,
        k_EStreamControlStopAudioData: CStopAudioDataMsg,
        k_EStreamControlStartVideoData: CStartVideoDataMsg,
        k_EStreamControlStopVideoData: CStopVideoDataMsg,
        k_EStreamControlSetSpectatorMode: CSetSpectatorModeMsg,
        k_EStreamControlSetKeymap: CSetKeymapMsg,
        k_EStreamControlSetActivity: CSetActivityMsg,
        k_EStreamControlSetCaptureSize: CSetCaptureSizeMsg,
        k_EStreamControlVideoEncoderInfo: CVideoEncoderInfoMsg,
    }

    def handle_frame(self, frame: Frame):
        header = frame.header
        payload = frame.body
        if header.pkt_type == PacketType.RELIABLE:
            msg_type = payload[0]
            if frame_should_encrypt(msg_type):
                try:
                    message = frame_decrypt(payload[1:], self.client.auth_token, self.recv_decrypt_sequence)
                except ValueError as e:
                    raise ValueError(
                        f'Failed to decode message (head {header}) {EStreamControlMessage.Name(msg_type)}: {e}')
                self.recv_decrypt_sequence += 1
                self.on_reliable(header.pkt_id, msg_type, message)
            else:
                self.on_reliable(header.pkt_id, msg_type, payload[1:])

    def on_reliable(self, pkt_id: int, msg_type: int, payload: bytes):
        msg_ctor = self.msg_types.get(msg_type, None)
        if not msg_ctor:
            print(f'Unrecognized type {EStreamControlMessage.Name(msg_type)}')
            return
        message = msg_ctor()
        try:
            message.ParseFromString(payload)
        except DecodeError as e:
            print(f'Failed to decode {payload.hex()} ({msg_type}): {e}')
            return
        if msg_type == k_EStreamControlServerHandshake:
            self.on_server_handshake(message)
        elif msg_type == k_EStreamControlAuthenticationResponse:
            self.on_auth_response(message)
        elif msg_type == k_EStreamControlNegotiationInit:
            self.on_negotiation_init(pkt_id, message)
        elif msg_type == k_EStreamControlNegotiationSetConfig:
            self.on_negotation_set_config(pkt_id, message)
        elif msg_type == k_EStreamControlShowCursor:
            # Move cursor location
            pass
        elif msg_type == k_EStreamControlSetIcon:
            # Set app icon
            pass
        elif msg_type == k_EStreamControlSetKeymap:
            # Set keymap
            pass
        elif msg_type == k_EStreamControlSetCursor:
            # Set keymap
            pass
        elif msg_type == k_EStreamControlVideoEncoderInfo:
            # Video encoder info (for display)
            pass
        elif msg_type == k_EStreamControlStartAudioData:
            self.client.add_channel(message.channel, Audio(self.client, message))
        elif msg_type == k_EStreamControlStopAudioData:
            self.client.remove_channel_by_type(Audio)
        elif msg_type == k_EStreamControlStartVideoData:
            self.client.add_channel(message.channel, Video(self.client, message))
        elif msg_type == k_EStreamControlStopVideoData:
            self.client.remove_channel_by_type(Video)
        elif msg_type == k_EStreamControlSetTitle:
            print(f'Set title {message.text}')
        else:
            print(f'unhandled {EStreamControlMessage.Name(msg_type)}: {message}')
            pass

    def on_server_handshake(self, message: CServerHandshakeMsg):
        mtu = message.info.mtu
        out_msg = CAuthenticationRequestMsg(version=k_EStreamVersionCurrent, steamid=get_steamid(),
                                            token=frame_hmac256(b'Steam In-Home Streaming', self.client.auth_token))
        self.send_reliable(k_EStreamControlAuthenticationRequest, out_msg)

    def on_auth_response(self, message: CAuthenticationResponseMsg):
        if message.result != 0:
            self.client.hangup()

    def on_negotiation_init(self, pkt_id: int, message: CNegotiationInitMsg):
        config = CNegotiatedConfig(reliable_data=message.reliable_data)
        for codec in message.supported_audio_codecs:
            if codec in [k_EStreamAudioCodecOpus]:
                config.selected_audio_codec = codec
        for codec in message.supported_video_codecs:
            supported_codecs = [k_EStreamVideoCodecH264, k_EStreamVideoCodecHEVC]
            if codec in supported_codecs:
                config.selected_video_codec = codec
        config.available_video_modes.extend([CStreamVideoMode(width=1920, height=1080,
                                                              refresh_rate_numerator=5994,
                                                              refresh_rate_denominator=100)])
        config.enable_remote_hid = True
        config.enable_touch_input = True
        client_cfg = CStreamingClientConfig()
        client_cfg.maximum_resolution_x = 0
        client_cfg.maximum_resolution_y = 0
        client_cfg.enable_hardware_decoding = True
        client_cfg.enable_performance_overlay = True
        client_cfg.enable_audio_streaming = True
        client_cfg.enable_performance_icons = True
        client_cfg.enable_microphone_streaming = True
        # client_cfg.enable_video_hevc = True

        client_caps = CStreamingClientCaps()
        client_caps.system_can_suspend = True
        # client_caps.supports_video_hevc = True
        client_caps.maximum_decode_bitrate_kbps = 30000
        client_caps.maximum_burst_bitrate_kbps = 90000
        client_caps.form_factor = k_EStreamDeviceFormFactorTV

        out_msg = CNegotiationSetConfigMsg(config=config, streaming_client_config=client_cfg,
                                           streaming_client_caps=client_caps)
        self.send_reliable(k_EStreamControlNegotiationSetConfig, out_msg, pkt_id)

    def on_negotation_set_config(self, pkt_id: int, message: CNegotiationSetConfigMsg):
        out_msg = CNegotiationCompleteMsg()
        self.send_reliable(k_EStreamControlNegotiationComplete, out_msg, pkt_id)

    def frame_should_encrypt(self, msg_type: int) -> bool:
        return msg_type not in [k_EStreamControlClientHandshake, k_EStreamControlServerHandshake,
                                k_EStreamControlAuthenticationRequest, k_EStreamControlAuthenticationResponse]
