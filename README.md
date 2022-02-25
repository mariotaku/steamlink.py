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

See [session/README.md](https://github.com/mariotaku/steamlink.py/tree/master/session)