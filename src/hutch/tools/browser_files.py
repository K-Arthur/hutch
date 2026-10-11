"""Bounded UTF-8 workspace transfers; no host file chooser or opaque download spool."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import time

from .filewrite import destination, parent_fd

MAX_FILE_BYTES = 4_000_000
MAX_TRANSFER_BYTES = 16_000_000
MAX_TRANSFERS = 8
TEXT_TYPES = {".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv", ".json": "application/json"}


def text_file(path: str, data: bytes) -> tuple[str, str]:
    mime = TEXT_TYPES.get(Path(path).suffix.lower())
    if mime is None:
        raise ValueError("browser transfers currently support .txt, .md, .csv and .json only")
    if len(data) > MAX_FILE_BYTES or b"\0" in data:
        raise ValueError("browser transfer must be UTF-8 text without NUL bytes, at most 4 MB")
    return data.decode("utf-8", errors="strict"), mime


def read_upload(ctx, path: str) -> tuple[bytes, dict]:
    decision = ctx.policy.check_path(path, ctx.workspace, write=False)
    if decision.verdict.value == "deny":
        raise ValueError(decision.reason)
    workspace, parts = destination(path, ctx.workspace)
    with parent_fd(workspace, parts) as parent:
        handle = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(handle, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE_BYTES:
                raise ValueError("upload must be one regular workspace file, without symlinks or hard links, at most 4 MB")
            data = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if identity(before) != identity(after) or len(data) != after.st_size:
        raise ValueError("upload source changed while reading; review again")
    text, mime = text_file(path, data)
    return data, {"path": "/".join(parts), "name": parts[-1], "mime_type": mime,
                  "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                  "revision": list(identity(after)), "preview": text[:2000], "preview_truncated": len(text) > 2000}


def read_download(sock, read_header, path, check) -> bytes:
    """Bound the actual plaintext UI response before any bytes reach Chromium or disk.

    A direct HTTP 200 with Content-Length and identity encoding is required. TLS
    remains Chromium-owned, so HTTPS transfers cannot use this narrower boundary.
    """
    import http.client
    import io

    sock.settimeout(2)
    deadline = time.monotonic() + 8
    check()
    header, extra = read_header(sock, check=check, deadline=deadline)
    if header is None:
        raise ValueError("download response missing")
    status, rest = header.split(b"\r\n", 1)
    if not status.startswith((b"HTTP/1.1 200 ", b"HTTP/1.0 200 ")):
        raise ValueError("download returned a non-200 response or redirect; inspect before retrying")
    headers = http.client.parse_headers(io.BytesIO(rest))
    lengths = headers.get_all("content-length", [])
    if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or int(lengths[0]) > MAX_FILE_BYTES:
        raise ValueError("download needs one Content-Length, at most 4 MB")
    length = int(lengths[0])
    if headers.get("transfer-encoding") or headers.get("content-encoding", "identity").lower() != "identity":
        raise ValueError("chunked or compressed browser downloads are unsupported")
    if headers.get("content-type", "").split(";", 1)[0].lower() not in set(TEXT_TYPES.values()):
        raise ValueError("download must have a supported text content type")
    if len(extra) > length:
        raise ValueError("download response exceeds its declared size")
    data = bytearray(extra)
    while len(data) < length:
        check()
        if time.monotonic() > deadline:
            raise ValueError("download exceeded its 8 second deadline")
        chunk = sock.recv(min(16_384, length - len(data)))
        if not chunk:
            raise ValueError("download response incomplete; inspect before retrying")
        data.extend(chunk)
    check()
    text_file(path, bytes(data))
    return bytes(data)
