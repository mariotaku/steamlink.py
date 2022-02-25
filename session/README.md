## Sequence

```mermaid
sequenceDiagram
  Client ->> Host: Discovery/Connect
  Note over Client: Send client connection ID
  Host ->> Client: Discovery/Connect ACK
  Note over Client: Got host connection ID, start client handshake
  Client ->> Host: Reliable/Control:ClientHandshake
  par Discovery Channel
    loop While True
      Host ->> Client: Unconnected/Discovery:PingRequest
      Client ->> Host: Unconnected/Discovery:PingResponse
    end
  end
  Host ->> Client: Reliable/Control:ServerHandshake
  Note over Client: Got mtu, start authentication
  Client ->> Host: Reliable/Control:AuthenticationRequest
  Host ->> Client: Reliable/Control:AuthenticationResponse
  Host ->> Client: Reliable/Control:NegotiationInit
  Note over Client: Got host supported audio/video codecs
  Client ->> Host: Reliable/Control:NegotiationSetConfig
  Note over Client: Send selected codecs and config
  Host ->> Client: Reliable/Control:NegotiationSetConfig
  Note over Client: Got final config, respond with complete
  Client ->> Host: Reliable/Control:NegotiationComplete
  par Audio Data Channel
    Host ->> Client: Reliable/Control:StartAudioData
    loop Not StopAudioData
      Host ->> Client: Unreliable/Data:Packet 
    end
  and Video Data Channel
    Host ->> Client: Reliable/Control:StartVideoData
    loop Not StopVideoData
      Host ->> Client: Unreliable/Data:Packet 
    end
  end
  Client ->> Host: Discovery/Disconnect
```

## Packet Structure

| Size in Bits  | Name             | Type    | Description                            |
|---------------|------------------|---------|----------------------------------------|
| 1             | has_crc          | boolean |                                        |
| 7             | type             | enum    | See types below                        |
| 8             | retransmit_count | uint8   |                                        |
| 8             | src_conn_id      | uint8   |                                        |
| 8             | dst_conn_id      | uint8   |                                        |
| 8             | channel          | uint8   |                                        |
| 16            | fragment_id      | int16   | Fragment index or count                |
| 16            | packet_id        | uint16  |                                        |
| 32            | send_timestamp   | uint32  |                                        |
| ...           | body             | bytes   | Body of the packet, might be encrypted |
| 32 if has_crc | crc              | uint32  | crc32c(packet\[:-4\])                  |

## Packet Types

### Unconnected (0)

### Connect (1)

```
has_crc = false
type = 1
payload = crc32c(b'Connect')
```

### Connect ACK (2)

### Unreliable (3)

`fragment_id` will be number of following fragments.

### Unreliable Frag (4)

### Reliable (5)

`fragment_id` will be number of following fragments. For encrypted message, decryption should be done on concatenated
message body.

### Reliable Frag (6)

### ACK (7)

ACK will be responded if the peer accepted a reliable/frag packet.

### Negative ACK, NACK (8)

NACK will be sent if the peer doesn't accept a reliable/frag packet.

### Disconnect (9)

After client or host send this message, connection will be terminated.

## Channels

### Discovery (0)

Discovery channel is for sending ping request/response.

#### Message Types

### Control (1)

Control channel is for sending handshake, performing authorization, sending controls and transferring input events.

#### Message Types

### Stats (2)

#### Message Types

### Data (3+)

Channels above 3 will be opened by message `k_EStreamControlStart***Data`. It will be closed by
message `k_EStreamControlStop***Data`.

#### Message Types
