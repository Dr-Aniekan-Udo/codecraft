import base64
import hashlib
import hmac
import time


class WebhookVerificationError(Exception):
    """The webhook cannot be trusted, so nothing may be written."""


_MAX_TIMESTAMP_AGE_SECONDS = 300


def verify_webhook_signature(
    secret: str,
    svix_id: str,
    svix_timestamp: str,
    signature_header: str,
    body: bytes,
) -> None:
    """Verify a Svix-signed webhook before its body is parsed."""
    try:
        timestamp = int(svix_timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("timestamp is not an integer") from exc

    if abs(time.time() - timestamp) > _MAX_TIMESTAMP_AGE_SECONDS:
        raise WebhookVerificationError("timestamp is outside the tolerated window")

    try:
        secret_bytes = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    except ValueError as exc:
        raise WebhookVerificationError("signing secret is not valid base64") from exc

    # Svix signs the untrusted headers and body together, so changing any part
    # of the request invalidates the signature.
    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest())

    provided: list[bytes] = []
    for entry in signature_header.split():
        version, separator, value = entry.partition(",")
        if version == "v1" and separator and value:
            provided.append(value.encode())

    if not any(hmac.compare_digest(expected, candidate) for candidate in provided):
        raise WebhookVerificationError("signature does not match")
