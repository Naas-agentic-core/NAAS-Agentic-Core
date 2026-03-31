import jwt
from fastapi import HTTPException, WebSocket

ALGORITHM = "HS256"


def extract_bearer_token(auth_header: str | None) -> str:
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    parts = auth_header.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    return parts[1]


def decode_user_id(token: str, secret_key: str) -> int:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        return int(user_id)

    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid user ID in token") from exc


def _parse_protocol_header(protocol_header: str | None) -> list[str]:
    if not protocol_header:
        return []
    return [protocol.strip() for protocol in protocol_header.split(",") if protocol.strip()]


def _extract_token_from_protocols(protocols: list[str]) -> str | None:
    if "jwt" not in protocols:
        return None
    try:
        jwt_index = protocols.index("jwt")
    except ValueError:
        return None
    if jwt_index + 1 >= len(protocols):
        return None
    return protocols[jwt_index + 1]


def extract_websocket_auth(websocket: WebSocket) -> tuple[str | None, str | None]:
    # 1. Try to extract from Authorization header (Injected by Gateway)
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip(), "jwt"

    # 2. Fallback to extracting from subprotocols (if direct connection)
    protocols = _parse_protocol_header(websocket.headers.get("sec-websocket-protocol"))
    token = _extract_token_from_protocols(protocols)
    if token:
        return token, "jwt"

    # 3. Fallback to query param
    fallback_token = websocket.query_params.get("token")
    return fallback_token, None
