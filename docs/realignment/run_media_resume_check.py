"""Phase 6 real-stack check: a paid media result survives a SIGKILL, and a real server finishes it.

What is real: the Hutch server process (`hutch serve` on a real port), its SQLite database, the
durable spool, the media store, the pinned transport and the HTTP calls between them. What is NOT
real: the provider. A stand-in HTTP server on loopback speaks the xAI and MiniMax wire shapes read
from vendor documentation. That makes this a test of Hutch's own crash recovery and ledger, not
evidence about any vendor, and every route it touches stays implemented-unverified.

  uv run --frozen --no-sync python docs/realignment/run_media_resume_check.py \
      --state /tmp/some/empty/dir --port 18895 --out docs/realignment/artifacts/provider-expansion-2026-11/phase6/media-resume-run.json

Steps: (1) a victim process submits a speech job (the stand-in answers and "bills"), then kills
itself before storing anything (the paid bytes are in the spool); (2) a real server starts on the same state directory and lists the
open job; (3) advance finishes it with exactly one provider request and the served bytes hash to the
stand-in's bytes and the spool entry is released; (4) a video job is advanced while the stand-in says pending, then done; (5) a
second video job is cancelled and, because xAI documents no cancel call, ends cancel_unconfirmed;
(6) a MiniMax image request answered with status 1026 ends as a refusal.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import signal
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def wav() -> bytes:
    data = b"\x00\x00" * 2400
    fmt = struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<I", 16) + fmt
            + b"data" + struct.pack("<I", len(data)) + data)


MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1" + b"\x00" * 16
WAV = wav()


class StandIn(http.server.BaseHTTPRequestHandler):
    counts: dict[str, int] = {}
    video_status = "pending"

    def log_message(self, *_args):
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        self.rfile.read(length)
        self.counts[self.path] = self.counts.get(self.path, 0) + 1
        if self.path == "/v1/tts":
            return self._send(200, WAV, "audio/wav")
        if self.path == "/v1/videos/generations":
            return self._json(200, {"request_id": f"vid-{self.counts[self.path]}"})
        if self.path == "/minimax/v1/image_generation":
            return self._json(200, {"base_resp": {"status_code": 1026, "status_msg": "input new_sensitive"}})
        self._json(404, {"error": {"message": "not found"}})

    def do_GET(self):
        self.counts[self.path.split("?")[0]] = self.counts.get(self.path.split("?")[0], 0) + 1
        if self.path.startswith("/v1/videos/"):
            body = {"status": StandIn.video_status}
            if StandIn.video_status == "done":
                body["video"] = {"url": f"http://127.0.0.1:{self.server.server_address[1]}/media/clip.mp4"}
            return self._json(200, body)
        if self.path == "/media/clip.mp4":
            return self._send(200, MP4, "video/mp4")
        self._json(404, {"error": {"message": "not found"}})


VICTIM = r"""
import os, signal, sys
from pathlib import Path
from hutch.config import get_config
from hutch.media import MediaJobService, MediaStorage
from hutch.media.backends import build_backends
from hutch.media.spool import MediaSpool
from hutch.store import Store
from hutch.models import Bot, Run, RunStatus, ApprovalMode

config = get_config()
store = Store(config)
kind, backend, prompt, key = sys.argv[1:5]
bot = Bot(name="media-check-" + key, model="xai/none", tools=["create_media"], approval_mode=ApprovalMode.ask)
store.create_bot(bot)
run = Run(bot_id=bot.id, prompt="media check", status=RunStatus.running)
store.create_run(run)
storage = MediaStorage(config)
service = MediaJobService(store, storage, backends=build_backends(config.state_dir, spool=MediaSpool(storage.root)))
row = service.submit(run_id=run.id, conversation_id=run.conversation_id, kind=kind, prompt=prompt,
                     idempotency_key=key, backend_hint=backend)
print(row["id"], row["status"], flush=True)
if len(sys.argv) > 5 and sys.argv[5] == "die":
    os.kill(os.getpid(), signal.SIGKILL)
"""


def http_json(method: str, url: str, timeout: float = 20.0):
    request = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--port", type=int, default=18895)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    state = Path(args.state)
    state.mkdir(parents=True, exist_ok=True)
    if any(state.iterdir()):
        raise SystemExit(f"refusing to run: {state} is not empty")

    standin = http.server.ThreadingHTTPServer(("127.0.0.1", 0), StandIn)
    threading.Thread(target=standin.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{standin.server_address[1]}"
    env = {**os.environ, "HUTCH_STATE_DIR": str(state), "PYTHONPATH": str(ROOT / "src"),
           "HUTCH_SANDBOX": "off"}
    for name in ("XAI_API_KEY", "MINIMAX_API_KEY", "OPENAI_API_KEY", "FAL_KEY"):
        env.pop(name, None)

    from hutch.connections import ConnectionBook  # after PYTHONPATH is set in this process too
    os.environ["HUTCH_STATE_DIR"] = str(state)
    book = ConnectionBook(state)
    book.add("xai", name="xai", base_url=f"{origin}/v1")
    book.set_key("xai", "sk-standin-secret-never-printed")
    book.add("minimax", name="minimax", base_url=f"{origin}/minimax/v1")
    book.set_key("minimax", "mm-standin-secret-never-printed")

    def victim(*argv: str, die: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-c", VICTIM, *argv, *(["die"] if die else [])],
                              env=env, capture_output=True, text=True, timeout=60)

    record: dict = {"date": time.strftime("%Y-%m-%d"), "provider": "stand-in HTTP server on loopback "
                    "(NOT a vendor): proves Hutch's recovery and ledger, nothing about any vendor",
                    "steps": []}

    def step(name: str, **facts) -> None:
        record["steps"].append({"step": name, **facts})
        print(f"[{name}] {facts}", flush=True)

    # 1. the victim submits a speech job and is killed before storing anything
    dead = victim("audio", "xai-speech:xai", "Hutch crash recovery check.", "k-speech", die=True)
    job_speech = dead.stdout.split()[0]
    step("victim-killed", returncode=dead.returncode, signal=-dead.returncode == signal.SIGKILL,
         job=job_speech, provider_tts_requests=StandIn.counts.get("/v1/tts", 0))
    assert dead.returncode == -signal.SIGKILL, dead.stderr

    # 2. a real server starts on the same state directory
    cli = ["-c", "from hutch.cli import app; app()"]
    subprocess.run([sys.executable, *cli, "init"], cwd=ROOT, env=env, check=True,
                   capture_output=True, timeout=120)
    server = subprocess.Popen([sys.executable, *cli, "serve", "--port", str(args.port)],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{args.port}"
    try:
        for _ in range(100):
            try:
                http_json("GET", f"{base}/api/v1/media/jobs")
                break
            except Exception:
                time.sleep(0.3)
        else:
            raise SystemExit("server did not start: " + server.stderr.read().decode()[-500:])
        listing = http_json("GET", f"{base}/api/v1/media/jobs")["jobs"]
        step("open-jobs", jobs=[(j["id"], j["status"], j["backend"]) for j in listing])

        # 3. advance finishes the orphaned speech job without a second provider request
        advanced = http_json("POST", f"{base}/api/v1/media/jobs/{job_speech}/advance")
        media = advanced["job"]["media"] or {}
        served = fetch_bytes(base + media["content_url"]) if media else b""
        step("advance-speech", action=advanced["action"], status=advanced["job"]["status"],
             sha256_served=hashlib.sha256(served).hexdigest(), sha256_expected=hashlib.sha256(WAV).hexdigest(),
             bytes_match=served == WAV, provider_tts_requests=StandIn.counts.get("/v1/tts", 0),
             spool_entries_after=sorted(p.name for p in (state / "media" / "spool").glob("spool_*")))

        # 4. a video job: pending, then done
        out = victim("video", "xai-video:xai", "waves on a shore", "k-video")
        assert out.stdout.strip(), out.stderr[-600:]
        job_video = out.stdout.split()[0]
        pending = http_json("POST", f"{base}/api/v1/media/jobs/{job_video}/advance")
        StandIn.video_status = "done"
        done = http_json("POST", f"{base}/api/v1/media/jobs/{job_video}/advance")
        vmedia = done["job"]["media"] or {}
        vserved = fetch_bytes(base + vmedia["content_url"]) if vmedia else b""
        step("advance-video", first=pending["action"], then=done["action"], status=done["job"]["status"],
             bytes_match=vserved == MP4, mime=vmedia.get("mime"))

        # 5. cancel: xAI documents no cancel call, so the honest end state is cancel_unconfirmed
        StandIn.video_status = "pending"
        out = victim("video", "xai-video:xai", "a second render", "k-video-2")
        job_cancel = out.stdout.split()[0]
        cancelled = http_json("POST", f"{base}/api/v1/media/jobs/{job_cancel}/cancel", timeout=30)
        step("cancel-video", status=cancelled["job"]["status"], error=(cancelled["job"]["error"] or "")[:120])

        # 6. a provider refusal found in a 200 body
        out = victim("image", "minimax-image:minimax", "a prompt the provider declines", "k-image")
        refused = http_json("GET", f"{base}/api/v1/media/jobs/{out.stdout.split()[0]}")
        step("refusal", status=refused["status"], error=(refused["error"] or "")[:120])

        everything = json.dumps(record) + json.dumps(listing) + json.dumps(advanced)
        record["secrets_in_record"] = any(s in everything for s in ("sk-standin-secret", "mm-standin-secret"))
        spool_left = record["steps"][2]["spool_entries_after"]
        ok = (advanced["action"] == "finalized" and served == WAV and StandIn.counts.get("/v1/tts") == 1
              and spool_left == []
              and done["action"] == "finalized" and vserved == MP4
              and cancelled["job"]["status"] == "cancel_unconfirmed" and refused["status"] == "refused"
              and not record["secrets_in_record"])
        record["passed"] = bool(ok)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        standin.shutdown()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(record, indent=2) + "\n")
    print("PASSED" if record["passed"] else "FAILED")
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
