from google.protobuf.message import Message

from protobuf.steammessages_remoteclient_discovery_pb2 import CMsgRemoteDeviceStreamingRequest, \
    k_EStreamDeviceFormFactorTV, k_EStreamInterfaceDefault, k_EStreamTransportUDP, k_EStreamInterfaceDesktop, \
    k_EStreamTransportUDPRelay, k_EStreamTransportSDR
from service.common import get_device_id, device_token, get_secret_key


def streaming_req(request_id: int) -> Message:
    message = CMsgRemoteDeviceStreamingRequest()
    device_id = get_device_id()
    message.client_id = device_id
    message.request_id = request_id
    message.form_factor = k_EStreamDeviceFormFactorTV
    message.enable_video_streaming = True
    message.enable_audio_streaming = True
    message.enable_input_streaming = True
    message.maximum_resolution_x = 1920
    message.maximum_resolution_y = 1080
    message.audio_channel_count = 2
    message.gamepad_count = 0
    # message.gamepad_count = 1
    # message.gamepads.append(CMsgRemoteDeviceStreamingRequest.ReservedGamepad(controller_type=2, controller_subtype=1))
    message.stream_desktop = True
    message.stream_interface = k_EStreamInterfaceDesktop
    message.supported_transport.extend([k_EStreamTransportUDP, k_EStreamTransportUDPRelay, k_EStreamTransportSDR])
    message.restricted = False
    message.device_token = device_token(device_id, get_secret_key())
    message.device_version = 'build 827'
    message.network_test = False
    message.gameid = 0
    message.pin = b''
    return message
