from __future__ import annotations

import hashlib
import io
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol, cast

from minio import Minio
from minio.error import S3Error


class ArtifactNotFoundError(KeyError):
    pass


class ArtifactCorruptionError(ValueError):
    pass


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("artifact datetime must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, set | frozenset):
        normalized = [_json_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("artifact numbers must be finite")
        return 0.0 if value == 0 else value
    if value is None or isinstance(value, str | int | bool):
        return value
    raise TypeError(f"unsupported artifact value: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        _json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def content_hash(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _validate_hash(value: str) -> None:
    if value.lower() == "latest":
        raise ValueError("latest artifact references are forbidden")
    prefix, separator, digest = value.partition(":")
    if (
        prefix != "sha256"
        or not separator
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        raise ValueError("content_hash must be a sha256:<hex> address")


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    content_hash: str
    size_bytes: int
    media_type: str

    def __post_init__(self) -> None:
        _validate_hash(self.content_hash)
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if not self.media_type.strip():
            raise ValueError("media_type must not be blank")


class ArtifactStore(Protocol):
    def put(self, payload: bytes, *, media_type: str) -> ArtifactManifest: ...

    def get(self, address: str) -> bytes: ...

    def exists(self, address: str) -> bool: ...

    def verify(self, manifest: ArtifactManifest) -> bool: ...


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self._media_types: dict[str, str] = {}

    def put(self, payload: bytes, *, media_type: str) -> ArtifactManifest:
        immutable = bytes(payload)
        address = content_hash(immutable)
        previous = self._objects.get(address)
        if previous is not None and previous != immutable:
            raise ArtifactCorruptionError("content address collision")
        previous_media_type = self._media_types.get(address)
        if previous_media_type is not None and previous_media_type != media_type:
            raise ValueError("immutable artifact media_type cannot be overwritten")
        self._objects[address] = immutable
        self._media_types[address] = media_type
        return ArtifactManifest(address, len(immutable), media_type)

    def get(self, address: str) -> bytes:
        _validate_hash(address)
        try:
            payload = self._objects[address]
        except KeyError as exc:
            raise ArtifactNotFoundError(address) from exc
        if content_hash(payload) != address:
            raise ArtifactCorruptionError(
                f"artifact {address} failed hash verification"
            )
        return bytes(payload)

    def exists(self, address: str) -> bool:
        _validate_hash(address)
        return address in self._objects

    def verify(self, manifest: ArtifactManifest) -> bool:
        try:
            payload = self.get(manifest.content_hash)
        except (ArtifactNotFoundError, ArtifactCorruptionError):
            return False
        return (
            len(payload) == manifest.size_bytes
            and self._media_types.get(manifest.content_hash) == manifest.media_type
        )


class MinioArtifactStore:
    def __init__(self, client: Minio, *, bucket: str) -> None:
        if not bucket.strip():
            raise ValueError("bucket must not be blank")
        self._client = client
        self._bucket = bucket

    @staticmethod
    def _key(address: str) -> str:
        _validate_hash(address)
        digest = address.removeprefix("sha256:")
        return f"sha256/{digest[:2]}/{digest}"

    def put(self, payload: bytes, *, media_type: str) -> ArtifactManifest:
        immutable = bytes(payload)
        address = content_hash(immutable)
        manifest = ArtifactManifest(address, len(immutable), media_type)
        key = self._key(address)
        if self.exists(address):
            if self.get(address) != immutable:
                raise ArtifactCorruptionError("content address collision")
            return manifest
        self._client.put_object(
            self._bucket,
            key,
            io.BytesIO(immutable),
            len(immutable),
            content_type=media_type,
            metadata={"content-hash": address},
        )
        if not self.verify(manifest):
            raise ArtifactCorruptionError("uploaded artifact failed verification")
        return manifest

    def get(self, address: str) -> bytes:
        key = self._key(address)
        try:
            response = self._client.get_object(self._bucket, key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                raise ArtifactNotFoundError(address) from exc
            raise
        try:
            payload = cast(bytes, response.read())
        finally:
            response.close()
            response.release_conn()
        if content_hash(payload) != address:
            raise ArtifactCorruptionError(
                f"artifact {address} failed hash verification"
            )
        return payload

    def exists(self, address: str) -> bool:
        key = self._key(address)
        try:
            self._client.stat_object(self._bucket, key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return False
            raise
        return True

    def verify(self, manifest: ArtifactManifest) -> bool:
        try:
            payload = self.get(manifest.content_hash)
            stat = self._client.stat_object(
                self._bucket, self._key(manifest.content_hash)
            )
        except (ArtifactNotFoundError, ArtifactCorruptionError):
            return False
        return (
            len(payload) == manifest.size_bytes
            and stat.size == manifest.size_bytes
            and stat.content_type == manifest.media_type
        )
