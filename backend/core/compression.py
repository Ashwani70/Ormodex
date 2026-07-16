"""Response compression, skipping media types that are already compressed.

Starlette's stock GZipMiddleware has no content-type awareness — it gzips
every response over `minimum_size` bytes, including PDFs (deflate-compressed
internally), XLSX/DOCX/ZIP (already a ZIP container), and JPEG/PNG images.
Re-gzipping those wastes CPU for near-zero size benefit (a few percent at
best, since their bytes are already high-entropy) and risks inflating tiny
already-compressed payloads slightly. JSON/HTML/CSV/plain text — this app's
actual API responses — compress 70-90%+ and are exactly what GZipMiddleware
is for.

SkipAlreadyCompressedGZipMiddleware is a drop-in replacement for
GZipMiddleware: same constructor signature, same negotiation (only engages
when the client sends "gzip" in Accept-Encoding), same minimum_size
threshold — it just adds one more gate, checked once the handler's
Content-Type header is known: skip gzip entirely for the media types in
_ALREADY_COMPRESSED_TYPES, otherwise behave exactly like GZipMiddleware.
"""
import gzip
import io

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_ALREADY_COMPRESSED_TYPES = frozenset({
    "application/pdf",
    "application/zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
})


class SkipAlreadyCompressedGZipMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 1000, compresslevel: int = 9) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            if "gzip" in headers.get("Accept-Encoding", ""):
                responder = _SkippingGZipResponder(self.app, self.minimum_size, self.compresslevel)
                await responder(scope, receive, send)
                return
        await self.app(scope, receive, send)


class _SkippingGZipResponder:
    """Same buffering strategy as Starlette's GZipResponder, plus a
    content-type gate: if the response's own Content-Type is already a
    compressed format, the buffered body is flushed through unmodified
    instead of gzipped. Bodies are still buffered up to the point the app
    finishes sending — same tradeoff GZipResponder already makes, since the
    gzip footer/CRC can't be written until every chunk is seen.
    """

    def __init__(self, app: ASGIApp, minimum_size: int, compresslevel: int) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.send: Send = _unattached_send
        self.initial_message: Message = {}
        self.started = False
        self.content_encoding_set = False
        self.skip_compression = False
        self.gzip_buffer = io.BytesIO()
        self.gzip_file = gzip.GzipFile(mode="wb", fileobj=self.gzip_buffer, compresslevel=compresslevel)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self.send_with_gzip)

    async def send_with_gzip(self, message: Message) -> None:
        message_type = message["type"]
        if message_type == "http.response.start":
            self.initial_message = message
            headers = Headers(raw=self.initial_message["headers"])
            self.content_encoding_set = "content-encoding" in headers
            content_type = headers.get("content-type", "").split(";")[0].strip().lower()
            self.skip_compression = content_type in _ALREADY_COMPRESSED_TYPES
        elif message_type == "http.response.body" and (self.content_encoding_set or self.skip_compression):
            if not self.started:
                self.started = True
                await self.send(self.initial_message)
            await self.send(message)
        elif message_type == "http.response.body" and not self.started:
            self.started = True
            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            if len(body) < self.minimum_size and not more_body:
                await self.send(self.initial_message)
                await self.send(message)
            else:
                self.gzip_file.write(body)
                if not more_body:
                    self.gzip_file.close()
                    body = self.gzip_buffer.getvalue()
                    headers = MutableHeaders(raw=self.initial_message["headers"])
                    headers["Content-Encoding"] = "gzip"
                    headers["Content-Length"] = str(len(body))
                    headers.add_vary_header("Accept-Encoding")
                    message["body"] = body
                await self.send(self.initial_message)
                await self.send(message)
        elif message_type == "http.response.body":
            # Remaining chunks of a response that's already been started.
            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            self.gzip_file.write(body)
            if not more_body:
                self.gzip_file.close()
                message["body"] = self.gzip_buffer.getvalue()
            else:
                message["body"] = b""
            await self.send(message)


async def _unattached_send(message: Message) -> None:
    raise RuntimeError("send awaitable not set")  # pragma: no cover
