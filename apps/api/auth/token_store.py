"""Encrypted OAuth token store, scoped per user (E4: tokens encrypted, never logged, tenant-scoped).

- Every value is encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using TOKEN_ENCRYPTION_KEY from the environment.
  Generate one with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
- Records are keyed by (user, provider): one user can never read another user's tokens.
- Nothing here logs or prints a token; repr() of the store and of records hides values.
- UserTokenStorage adapts the store to the MCP SDK's TokenStorage protocol, so the SDK's OAuth 2.1 client
  (PKCE, dynamic client registration, refresh) persists tokens only through this file, encrypted.
"""
import json
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

DEFAULT_PATH = Path(os.getenv("TOKEN_STORE_PATH", "data/processed/oauth_tokens.json"))


class TokenStoreError(RuntimeError):
    pass


class EncryptedTokenStore:
    def __init__(self, path: Path = DEFAULT_PATH, key: str | bytes | None = None):
        key = key or os.getenv("TOKEN_ENCRYPTION_KEY")
        if not key:
            raise TokenStoreError("TOKEN_ENCRYPTION_KEY is not set; refusing to store OAuth tokens unencrypted")
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        self.path = Path(path)
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"EncryptedTokenStore(path={self.path!s}, entries=<hidden>)"

    def _load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    @staticmethod
    def _key(user: str, provider: str, kind: str) -> str:
        if not user or not provider:
            raise TokenStoreError("tokens are always scoped to a user and a provider")
        return f"{user}|{provider}|{kind}"

    def put(self, user: str, provider: str, kind: str, value: dict) -> None:
        with self._lock:
            data = self._load()
            data[self._key(user, provider, kind)] = self._fernet.encrypt(json.dumps(value).encode()).decode()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            tmp.replace(self.path)

    def get(self, user: str, provider: str, kind: str) -> dict | None:
        blob = self._load().get(self._key(user, provider, kind))
        if blob is None:
            return None
        try:
            return json.loads(self._fernet.decrypt(blob.encode()))
        except InvalidToken as e:
            raise TokenStoreError("cannot decrypt stored token (wrong TOKEN_ENCRYPTION_KEY?); reconnect the account") from e

    def delete(self, user: str, provider: str) -> None:
        with self._lock:
            data = {k: v for k, v in self._load().items() if not k.startswith(f"{user}|{provider}|")}
            self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def connected(self, user: str, provider: str) -> bool:
        return self._key(user, provider, "tokens") in self._load()


class UserTokenStorage:
    """The MCP SDK TokenStorage protocol for one (user, provider) pair."""

    def __init__(self, store: EncryptedTokenStore, user: str, provider: str):
        self.store, self.user, self.provider = store, user, provider

    def __repr__(self) -> str:
        return f"UserTokenStorage(user={self.user!r}, provider={self.provider!r})"

    async def get_tokens(self) -> OAuthToken | None:
        v = self.store.get(self.user, self.provider, "tokens")
        return OAuthToken.model_validate(v) if v else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.store.put(self.user, self.provider, "tokens", tokens.model_dump(mode="json", exclude_none=True))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        v = self.store.get(self.user, self.provider, "client")
        return OAuthClientInformationFull.model_validate(v) if v else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.store.put(self.user, self.provider, "client", client_info.model_dump(mode="json", exclude_none=True))
