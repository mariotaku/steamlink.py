# Reference Implementation for SteamLink Protocol

## Encryption & Decryption

### Symmetric Encryption & Decryption

### Asymmetric Encryption

```
RSA-PKCS1-OAEP(plain, key, hash=SHA1)
```

## Service Discovery

## Pairing

### Sequence

```mermaid
sequenceDiagram
  Client ->> Host: AuthorizationRequest
  Host ->> Client: AuthorizationResponse
  loop While AuthorizationInProgress
    Client ->> Host: AuthorizationRequest
    Host ->> Client: AuthorizationResponse
  end
```

### Results

## Requesting Stream

### Sequence

```mermaid
sequenceDiagram
  Client ->> Host: StreamingRequest
  par Host to Client
    Host ->> Client: StreamingResponse
    loop While StreamingInProgress
      Client ->> Host: StreamingRequest
      Host ->> Client: StreamingResponse
    end
  and Host to Client
    Host ->> Client: ProofRequest
    Client ->> Host: ProofResponse
  end
```

### Results

## Opening Stream

### Sequence

```mermaid
sequenceDiagram
  Client ->> Host: Connect
  Host ->> Client: Connect ACK
  par Host to Client
    loop While True
      Host ->> Client: Unconnected/Discovery:PingRequest
      Client ->> Host: Unconnected/Discovery:PingResponse
    end
  end
  Client ->> Host: Reliable/Control:ClientHandshake
  Host ->> Client: Reliable/Control:ServerHandshake
  Client ->> Host: Reliable/Control:AuthenticationRequest
  Host ->> Client: Reliable/Control:AuthenticationResponse
  Host ->> Client: Reliable/Control:NegotiationInit
  Client ->> Host: Reliable/Control:NegotiationSetConfig
  Host ->> Client: Reliable/Control:NegotiationSetConfig
  Client ->> Host: Reliable/Control:NegotiationComplete
  par Host to Client
    Host ->> Client: Reliable/Control:StartAudioData
    loop Not StopAudioData
      Host ->> Client: Unreliable/Data:Packet 
    end
  and Host to Client
    Host ->> Client: Reliable/Control:StartVideoData
    loop Not StopVideoData
      Host ->> Client: Unreliable/Data:Packet 
    end
  end
  Client ->> Host: Disconnect
```

### Packet Types

#### Connect

```
has_crc = false
type = 1
payload = crc32c(b'Connect')
```

#### Connect ACK

#### Unreliable

`fragment_id` will be number of following fragments.

#### Unreliable Frag

#### Reliable

`fragment_id` will be number of following fragments. For encrypted message, decryption should be done on concatenated
message body.

#### Reliable Frag

#### ACK

ACK will be responded if the peer accepted a reliable/frag packet.

#### Negative ACK (NACK)

NACK will be sent if the peer doesn't accept a reliable/frag packet.

#### Disconnect

After client or host send this message, connection will be terminated.
