# Discoverability, public surfaces and answer-engine readiness

This document records where Hutch is publicly discoverable, which facts each
surface may state, how the surfaces are verified, and what is intentionally
deferred. It complements [marketing-site.md](marketing-site.md), which owns the
site's claim wording, and [brand-assets.md](brand-assets.md), which owns artwork.

## Public surfaces

| Surface | Location | Owner | Update trigger |
|---|---|---|---|
| Source repository | https://github.com/K-Arthur/hutch | maintainer | every push to main |
| Marketing site | https://k-arthur.github.io/hutch/ | maintainer | website/ change; deploy runs from .github/workflows/pages.yml |
| Canonical URL | https://k-arthur.github.io/hutch/ | maintainer | host or custom domain change |
| Sitemap | https://k-arthur.github.io/hutch/sitemap.xml | maintainer | new site pages or lastmod change |
| Answer-engine context | https://k-arthur.github.io/hutch/llms.txt | maintainer | capability, licence or availability change |
| Crawler policy | website/robots.txt (origin-root caveat below) | maintainer | crawl-policy change only |
| Vulnerability policy | https://k-arthur.github.io/hutch/.well-known/security.txt | maintainer | contact or scope change |
| Repository topics | 20 topics in the GitHub About panel | maintainer | quarterly review or positioning change |
| Social preview | GitHub Settings > General > Social preview (manual upload) | maintainer | brand change |
| Releases | GitHub Releases, source tags only | maintainer | release or pre-release |

## Claim rules

Every public surface follows [the claim register](../.pipeline/marketing/2026-10/CLAIM-REGISTER.md)
and the tone rules in [marketing-site.md](marketing-site.md). In short: no
superlatives, benchmarks, testimonials, star counts, "production-ready",
"free forever" or absolute privacy claims. The stage term is "development
preview". Software is MIT-licensed; model usage is billed by the provider the
operator chooses.

## GitHub Pages caveats that affect SEO

- The site is a project page under /hutch/. All links in website/ are
  subpath-relative, which is required: a root-absolute /assets/... reference
  would 404 on Pages.
- Compliant crawlers read robots.txt only at the origin root
  (https://k-arthur.github.io/). Files under /hutch/ are not consulted. The
  repository copy documents intent and becomes effective only with a custom
  domain at the origin root.
- The same limitation applies to /.well-known/security.txt at the origin root.
  The file is still served and is correct for a future custom domain.
- GitHub Pages fixes cache headers (observed max-age=600) and does not accept
  custom headers or redirects. Cache-busting uses the existing ?v=<sha8> query
  convention on assets.
- Verification for Search Console and Bing Webmaster Tools must use a URL
  prefix property, not DNS verification (the github.io DNS zone is not ours).
  HTML-file or meta-tag verification is compatible with an Actions deployment.
- IndexNow is possible with a key file under /hutch/ and a keyLocation scoped to
  that path. Google does not participate in IndexNow.
- The site is published with an Actions artifact, so Jekyll processing is
  skipped; website/.nojekyll is kept for branch-deploy safety.

## Verified checks

Run these before claiming a public-surface change is complete:

1. Site crawl and metadata: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py`
   (exit 0; canonical true; sitemap 200; 8 og and 4 twitter tags; FAQ parity
   20/20; JSON-LD blocks parse; no internal 404s except deferred ones).
2. Structured data and claim parity: `uv run --frozen --no-sync pytest -q tests/e2e/test_website.py::test_structured_data_and_discovery_metadata_match_the_page`.
3. Absolute-URL consistency: the canonical, og:url, og:image and twitter:image
   values are absolute and carry the deployed origin. When a custom domain
   replaces github.io, search for the old origin before merging:
   `rg -n "k-arthur.github.io" README.md SECURITY.md website docs`.
4. Links: every link added to README or docs resolves in a fresh checkout.
5. GitHub state: topics, description, homepage, Discussions, secret scanning,
   push protection, private vulnerability reporting and Dependabot security
   updates enabled. Social preview requires a manual upload.

## Manual steps recorded for the maintainer

- Upload `website/assets/github-social-preview-1280x640.png` at GitHub
  Settings > General > Social preview (the API exposes no upload endpoint).
- Create Search Console and Bing Webmaster Tools URL-prefix properties for
  https://k-arthur.github.io/hutch/ with HTML verification, then submit
  sitemap.xml and review the Search Console Generative AI performance report.
- After a custom domain is chosen: add the domain in Pages, create CNAME and
  DNS records, enable HTTPS, replace the deployed origin in the four absolute
  head tags plus sitemap.xml, llms.txt, security.txt and this document, keep
  redirects, and re-verify both consoles.
- Recheck the 20 topics quarterly; keep them lowercase, hyphenated and honest.

## What is deliberately not done

- No analytics or tracking script is added. Measurement relies on the
  maintainer's Search Console, Bing and server-side referrer data.
- No blog, comparison page or programmatic page generation. The site remains
  one route until there is unique, evidence-backed content to publish.
- No star, watch or visitor-count claims; counts are not evidence of quality.
- No training-crawler opt-out. The current recorded policy allows all crawlers,
  including answer engines.
- No custom domain yet. github.io is the real, temporary origin; a custom
  domain migration is a separate decision with the steps above.
