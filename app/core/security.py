import hashlib
import hmac
import secrets


def hash_api_key(api_key: str) -> str:
    """Deterministic SHA-256 hash of an API key for storage and lookup."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_api_key(api_key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(api_key), stored_hash)


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)
