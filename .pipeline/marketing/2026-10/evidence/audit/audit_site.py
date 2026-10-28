#!/usr/bin/env python3
"""Phase 1 audit — serve website/ locally and measure the machine layer.

Re-run:  uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py
Outputs: JSON report to stdout; screenshots are taken separately by capture_site.py.
Read-only against the repo; writes nothing outside this evidence dir.
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SITE = REPO / "website"
PORT = 8899
BASE = f"http://127.0.0.1:{PORT}"

UAS = {
    "default": "Mozilla/5.0 (compatible; audit-script)",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Bingbot": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "OAI-SearchBot": "OAI-SearchBot/1.0 (+https://openai.com/searchbot)",
    "ClaudeBot": "ClaudeBot/1.0",
    "PerplexityBot": "PerplexityBot/1.0",
}


def get(path, ua=None):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": ua or UAS["default"]})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b""


class HeadAudit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.metas = []          # (attrs dict)
        self.links = []          # rel/href/type attrs
        self.h1 = 0
        self.ids = set()
        self.hrefs = []
        self.srcs = []
        self.srcsets = []
        self._in_title = False
        self.jsonld_blocks = []
        self._in_jsonld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            self.links.append(a)
        elif tag == "h1":
            self.h1 += 1
        elif tag == "a" and "href" in a:
            self.hrefs.append(a["href"])
        elif tag in ("img", "script") and "src" in a:
            self.srcs.append(a["src"])
        elif tag == "img" and "srcset" in a:
            self.srcsets.append(a["srcset"])
        elif tag == "source" and "srcset" in a:
            self.srcsets.append(a["srcset"])
        if tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld = True
            self.jsonld_blocks.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_jsonld = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_jsonld and self.jsonld_blocks:
            self.jsonld_blocks[-1] += data


class DetailsAudit(HTMLParser):
    """Extract (summary text, body text) pairs from details.faq-item elements."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self._depth = 0
        self._in_summary = 0
        self._cur = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "details" and "faq-item" in cls:
            self._depth = 1
            self._cur = {"summary": "", "content": ""}
        elif self._depth:
            if tag == "details":
                self._depth += 1
            if tag == "summary":
                self._in_summary += 1

    def handle_endtag(self, tag):
        if not self._depth:
            return
        if tag == "summary" and self._in_summary:
            self._in_summary -= 1
        elif tag == "details":
            self._depth -= 1
            if self._depth == 0:
                self.items.append(self._cur)
                self._cur = None

    def handle_data(self, data):
        if not self._depth or not self._cur:
            return
        t = " ".join(data.split())
        if not t:
            return
        if self._in_summary:
            self._cur["summary"] += t
        else:
            self._cur["content"] += " "
            self._cur["content"] += t


def norm(s):
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2014", "-").replace("\u2013", "-").replace("&rsquo;", "'")
    return " ".join(s.split())


def main():
    report = {}
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "-d", str(SITE)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    try:
        # A. crawler-UA parity (static server should treat all identically)
        ua_results = {}
        for name, ua in UAS.items():
            status, headers, body = get("/", ua)
            ua_results[name] = {
                "status": status,
                "bytes": len(body),
                "server": headers.get("Server", ""),
                "content_type": headers.get("Content-Type", ""),
            }
        report["ua_parity"] = ua_results

        # B. internal link/asset fetch
        status, _, html_bytes = get("/")
        html = html_bytes.decode("utf-8")
        p = HeadAudit()
        p.feed(html)
        internal = set()
        for h in p.hrefs + p.srcs:
            if h.startswith("#") or h.startswith("data:") or h.startswith("http"):
                continue
            internal.add(re.sub(r"\?.*$", "", h))
        for s in p.srcsets:
            for part in s.split(","):
                u = part.strip().split(" ")[0]
                if u and not u.startswith("http") and not u.startswith("data:"):
                    internal.add(re.sub(r"\?.*$", "", u))
        # agent frame set referenced by site.js
        frames = [f"assets/agent/f{c}-p{r}.webp" for c in range(7) for r in range(3)]
        internal.update(frames)
        internal.update(["robots.txt", "llms.txt", "sitemap.xml", "security.txt"])
        fetch = {}
        for path in sorted(internal):
            st, _, body = get("/" + path)
            fetch[path] = {"status": st, "bytes": len(body)}
        report["fetches"] = fetch
        report["broken"] = {k: v for k, v in fetch.items() if v["status"] != 200}

        # C. anchor integrity
        anchors = {h[1:] for h in p.hrefs if h.startswith("#") and len(h) > 1}
        report["anchors_missing"] = sorted(anchors - p.ids)
        report["anchors_total"] = len(anchors)

        # D. head inventory
        metas = p.metas
        def meta_get(key, attr="name"):
            for m in metas:
                if m.get(attr) == key:
                    return m.get("content", "")
            return None
        og = {m.get("property"): m.get("content") for m in metas if m.get("property", "").startswith("og:")}
        tw = {m.get("name"): m.get("content") for m in metas if m.get("name", "").startswith("twitter:")}
        report["head"] = {
            "title": p.title,
            "title_len": len(p.title),
            "description": meta_get("description"),
            "description_len": len(meta_get("description") or ""),
            "canonical": any(l.get("rel") == "canonical" for l in p.links),
            "robots_meta": meta_get("robots"),
            "og": og,
            "twitter": tw,
            "h1_count": p.h1,
            "lang": "en" if 'lang="en"' in html else "MISSING",
            "stylesheet_links": [l.get("href") for l in p.links if l.get("rel") == "stylesheet"],
        }

        # E. JSON-LD
        blocks = []
        for raw in p.jsonld_blocks:
            try:
                data = json.loads(raw)
                blocks.append({"ok": True, "type": data.get("@type"), "keys": sorted(data.keys())})
                if data.get("@type") == "SoftwareApplication":
                    report["software_app"] = {
                        "name": data.get("name"),
                        "operatingSystem": data.get("operatingSystem"),
                        "softwareVersion": data.get("softwareVersion"),
                        "license": data.get("license"),
                        "feature_count": len(data.get("featureList", [])),
                        "dateModified": data.get("dateModified"),
                    }
                if data.get("@type") == "FAQPage":
                    faqld = data.get("mainEntity", [])
            except json.JSONDecodeError as e:
                blocks.append({"ok": False, "error": str(e)})
        report["jsonld"] = blocks

        # F. FAQ visible parity
        d = DetailsAudit()
        d.feed(html)
        visible = {norm(i["summary"]): norm(i["content"]) for i in d.items}
        parity = []
        for q in faqld:
            qs = norm(q["name"])
            ans = norm(q["acceptedAnswer"]["text"])
            vis = visible.get(qs)
            parity.append({
                "question": qs[:60],
                "in_visible": vis is not None,
                "answer_matches_visible": vis == ans if vis else False,
            })
        report["faq_parity"] = {
            "jsonld_count": len(faqld),
            "visible_count": len(d.items),
            "mismatches": [x for x in parity if not x["in_visible"] or not x["answer_matches_visible"]],
        }

        # G. downloads.json
        st, _, dj = get("/downloads.json")
        djson = json.loads(dj)
        gh_links = sorted({h for h in p.hrefs if "github.com" in h})
        report["downloads_manifest"] = {
            "status": st,
            "repository": djson["source"]["repository"],
            "setup": djson["source"]["setup"],
            "channel": djson.get("channel"),
            "platforms": [{"id": x["id"], "artifacts": len(x["artifacts"])} for x in djson["platforms"]],
            "github_links_in_html": gh_links,
        }

        # H. machine files
        report["llms_txt"] = {
            "status": get("/llms.txt")[0],
            "mentions_github": "github.com" in get("/llms.txt")[2].decode(),
            "lines": get("/llms.txt")[2].decode().count("\n") + 1,
        }
        report["robots_txt"] = get("/robots.txt")[2].decode()
    finally:
        proc.terminate()
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
