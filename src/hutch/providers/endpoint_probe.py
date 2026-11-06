"""Which layer of a model endpoint failed? Address policy, DNS, connect, TLS, key, or the model list.

"Cannot connect - is the server running?" is the wrong sentence for most real failures: the server is running and
speaks plain HTTP on a port the URL calls https, or it wants a key, or it serves its API under ``/v1`` and the URL
stops short of it. This probe walks the layers in order, stops at the first that fails, and says what that layer
means. It makes no inference request and spends no tokens; the key, if any, goes only to the model-list URL of the
configured origin, through the same pinned transport the runtime uses, and never appears in a result.
"""

from __future__ import annotations

import socket
import ssl
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from .endpoint_policy import EndpointRefused, vet
from .pinned_transport import PinnedTransport, refuse_unsafe_transport

LAYERS = ("address", "dns", "connect", "tls", "key", "models")
_ENGINE_ADVICE = {
    "ollama": ("This is an Ollama server behind its OpenAI-compatible /v1 endpoint, which cannot set the context "
               "window per request (Ollama defaults to 4k tokens under 24 GiB of VRAM). Use the Ollama route so "
               "Hutch sets the window, or create a model with a larger num_ctx."),
}


@dataclass
class Layer:
    name: str
    ok: bool
    detail: str


@dataclass
class ProbeReport:
    layers: list[Layer] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    engine: str = ""
    advice: str = ""
    suggested_base: str = ""

    @property
    def failed(self) -> Optional[Layer]:
        return next((layer for layer in self.layers if not layer.ok), None)

    @property
    def ok(self) -> bool:
        return self.failed is None

    def summary(self) -> str:
        bad = self.failed
        return f"{bad.name}: {bad.detail}" if bad else f"all layers passed; {len(self.models)} model(s) listed"


def _fail(report: ProbeReport, name: str, detail: str) -> ProbeReport:
    report.layers.append(Layer(name, False, detail))
    return report


def _tls_detail(exc: ssl.SSLError, host: str) -> str:
    text = str(exc)
    if isinstance(exc, ssl.SSLCertVerificationError):
        return (f"the certificate for {host} is not trusted ({exc.verify_message}). Hutch keeps certificate checks "
                "on; add the issuing CA to the system trust store or set SSL_CERT_FILE, or use http:// on a "
                "network you trust")
    if "WRONG_VERSION_NUMBER" in text or "record layer" in text or "UNKNOWN_PROTOCOL" in text:
        return f"{host}'s port is up but speaks plain HTTP, not TLS: use http:// in the endpoint"
    return f"the TLS handshake with {host} failed ({exc.reason or type(exc).__name__})"


def _connect(ips: list[str], port: int, timeout: float, tls_host: Optional[str]) -> tuple[str, str]:
    """('', '') when a connection (and TLS, when asked) succeeded, else (layer, detail) for the last address tried."""
    problem = ("connect", "no address answered")
    for ip in ips:
        try:
            with socket.create_connection((ip, port), timeout=timeout) as raw:
                if tls_host is None:
                    return "", ""
                try:
                    with ssl.create_default_context().wrap_socket(raw, server_hostname=tls_host):
                        return "", ""
                except ssl.SSLError as exc:
                    return "tls", _tls_detail(exc, tls_host)
        except ConnectionRefusedError:
            problem = ("connect", f"nothing is listening on {ip}:{port} (connection refused)")
        except (TimeoutError, socket.timeout):
            problem = ("connect", f"{ip}:{port} did not answer within {timeout:g}s (a firewall, or the wrong host)")
        except OSError as exc:
            problem = ("connect", f"cannot reach {ip}:{port} ({exc.strerror or type(exc).__name__})")
    return problem


def _get(client: Any, url: str, key: str) -> Any:
    return client.get(url, headers={"Authorization": f"Bearer {key}"} if key else {})


def _model_ids(response: Any) -> Optional[list[str]]:
    try:
        rows = response.json().get("data")
    except (ValueError, AttributeError):
        return None
    ids = [row.get("id") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else None
    return [i for i in ids if isinstance(i, str)] if ids is not None else None


def _models_layer(report: ProbeReport, client: Any, base: str, models_url: str, key: str) -> ProbeReport:
    try:
        response = _get(client, models_url, key)
    except EndpointRefused as exc:
        return _fail(report, "address", str(exc))
    except Exception as exc:  # noqa: BLE001 - a transport fault the layers above did not predict
        hint = (" The port accepted a connection but did not answer HTTP: it may expect https://."
                if models_url.startswith("http://") else "")
        return _fail(report, "models", f"the request failed ({type(exc).__name__}).{hint}".replace("..", "."))
    status = response.status_code
    if status in (401, 403):
        report.layers.append(Layer("key", False, "reachable, but the API key was rejected (or the server needs one: a "
                                                 "protected server answers 401/403 on /v1/models)"))
        return report
    report.layers.append(Layer("key", True, "no key sent" if not key else "the server did not refuse the key (a server that does not check keys answers the same way)"))
    ids = _model_ids(response) if status == 200 else None
    if ids is not None:
        report.models = ids
        report.layers.append(Layer("models", True, f"{len(ids)} model(s) listed"))
        return report
    detail = (f"the redirect to {response.headers.get('location', 'another URL')} was not followed (a key would go "
              "to that host); set the endpoint to the final URL" if 300 <= status < 400
              else f"{models_url} answered HTTP {status}, not a model list")
    _suggest_v1(report, client, base, key)
    return _fail(report, "models", detail + (f". The same server lists its models under {report.suggested_base}/models: "
                                             f"set the endpoint to {report.suggested_base}"
                                             if report.suggested_base else ""))


def _suggest_v1(report: ProbeReport, client: Any, base: str, key: str) -> None:
    if base.rstrip("/").endswith("/v1"):
        return
    try:
        ids = _model_ids(_get(client, base.rstrip("/") + "/v1/models", key))
    except Exception:  # noqa: BLE001 - the suggestion is best effort
        return
    if ids is not None:
        report.suggested_base = base.rstrip("/") + "/v1"


def identify_engine(origin: str, *, client: Any = None, timeout: float = 3.0,
                    resolver: Optional[Callable[..., list]] = None) -> tuple[str, str]:
    """``(engine, advice)`` named only from the server's own answer, never from its port. No key is sent."""
    import httpx
    try:
        with (nullcontext(client) if client is not None
              else httpx.Client(transport=PinnedTransport(resolver=resolver), timeout=timeout)) as http:
            response = http.get(origin.rstrip("/") + "/api/version")
            if response.status_code == 200 and isinstance(response.json().get("version"), str):
                return "ollama", _ENGINE_ADVICE["ollama"]
    except Exception:  # noqa: BLE001 - identification is an extra; its failure is not a failed endpoint
        pass
    return "", ""


def probe_endpoint(base_url: str, *, key: str = "", models_url: str = "", timeout: float = 5.0,
                   resolver: Optional[Callable[..., list]] = None, identify: bool = False) -> ProbeReport:
    """Walk the layers for one endpoint root such as ``http://host:8000/v1``."""
    import httpx
    report, parts = ProbeReport(), urlsplit(base_url)
    host, https = (parts.hostname or ""), parts.scheme == "https"
    port = parts.port or (443 if https else 80)
    try:
        vetted = vet(host, port, resolver=resolver)
        refuse_unsafe_transport(parts.scheme, vetted[0][1], {"authorization": key} if key else {})
    except EndpointRefused as exc:
        return _fail(report, "address" if exc.layer == "policy" else "dns", str(exc))
    report.layers += [Layer("address", True, f"{host} resolves to {vetted[0][0]} ({vetted[0][1]})"),
                      Layer("dns", True, "resolved")]
    layer, detail = _connect([ip for ip, _ in vetted], port, timeout, host if https else None)
    if layer:
        return _fail(report, layer, detail)
    report.layers.append(Layer("connect", True, f"{vetted[0][0]}:{port} accepted the connection"))
    if https:
        report.layers.append(Layer("tls", True, "the certificate was verified"))
    with httpx.Client(transport=PinnedTransport(resolver=resolver), timeout=timeout) as client:
        _models_layer(report, client, base_url, models_url or base_url.rstrip("/") + "/models", key)
        if identify and report.ok:
            report.engine, report.advice = identify_engine(f"{parts.scheme}://{parts.netloc}", client=client)
    return report
