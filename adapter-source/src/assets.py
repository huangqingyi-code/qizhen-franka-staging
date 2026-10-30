"""Bounded, byte-addressed access to artifacts; never accept caller file paths."""

import base64
import codecs
import hashlib
import mimetypes


def file_signature(path):
    value = path.stat()
    return [value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_artifact(store, args):
    path = store.artifact(args["artifact_id"])
    record = store.data["artifacts"][args["artifact_id"]]
    size = path.stat().st_size
    offset = args.get("offset", 0)
    if offset > size:
        raise ValueError("ARTIFACT_OFFSET_OUT_OF_RANGE")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoding = args.get("encoding", "auto")
    if encoding == "auto":
        encoding = "utf-8" if mime.startswith("text/") or path.suffix in {".json", ".yaml", ".yml", ".log", ".ribbon_guard", ".svg"} else "base64"
    with path.open("rb") as stream:
        stream.seek(offset)
        chunk = stream.read(args.get("max_bytes", 32768))
    consumed = len(chunk)
    if encoding == "utf-8":
        try:
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            content = decoder.decode(chunk, final=offset + len(chunk) == size)
            consumed -= len(decoder.getstate()[0])
            if chunk and not consumed:
                raise ValueError("BYTE_LIMIT_TOO_SMALL_FOR_UTF8_CHARACTER")
        except UnicodeDecodeError:
            if args.get("encoding", "auto") != "auto":
                raise ValueError("INVALID_UTF8_CONTENT_OR_OFFSET") from None
            encoding, content = "base64", base64.b64encode(chunk).decode("ascii")
    else:
        content = base64.b64encode(chunk).decode("ascii")
    next_offset = offset + consumed
    return {**{k: v for k, v in record.items() if k not in {"path", "_signature"}},
            "artifact_id": args["artifact_id"], "mime_type": mime, "encoding": encoding,
            "content": content, "offset": offset, "bytes_returned": consumed,
            "next_offset": next_offset if next_offset < size else None,
            "truncated": next_offset < size}
