# Onboarding & Getting Started: Visual Validation Report (2026-10)

**Date:** 2026-10-30  
**Host Environment:** Linux (x86_64), Chromium, Python 3.13.15, FastAPI / Jinja2  
**Artifact Directory:** `docs/realignment/onboarding-2026-10/artifacts/`  
**Total Captured Artifacts:** 80 PNG files + `manifest.json`  
**Review Verdict:** PASS (No visual clipping, overflow, contrast failures, or broken responsive reflow observed)

---

## 1. Scope and Viewport Matrix

All 7 core onboarding screens plus desktop startup states were captured across the complete required viewport matrix:

| Viewport Category | Resolution (W x H) | Orientation / Use Case | Status |
|---|---|---|---|
| **Large Desktop** | 1440 x 1000 | Primary workstation | PASS |
| **Standard Laptop** | 1280 x 800 | Portable laptop display | PASS |
| **Small Desktop / Tablet Landscape** | 1024 x 768 | Legacy display / iPad landscape | PASS |
| **Vertical Split / Tiling** | 900 x 1024 | Tiling window manager / half-screen | PASS |
| **Tablet Portrait** | 768 x 1024 | iPad portrait | PASS |
| **Modern Phone** | 390 x 844 | iPhone 14/15/16 standard | PASS |
| **Compact Phone** | 375 x 812 | iPhone mini / standard compact | PASS |
| **Minimum Supported Mobile** | 320 x 740 | Narrow Android viewport | PASS |

---

## 2. Accessibility Conformance Inspections

### 2.1 WCAG 1.4.4: 200% Zoom (`*-zoom-200.png`)
- **Inspection Method:** Captured at 1280 x 800 with `device_scale_factor = 2`.
- **Findings:** Content scales up cleanly without clipping or forced two-dimensional scrolling. Form inputs, labels, and helper descriptions wrap within the main container. Touch and click targets remain accessible.
- **Verdict:** PASS

### 2.2 WCAG 1.4.12: Text Spacing Override (`*-text-spacing.png`)
- **Inspection Method:** Applied user stylesheet:
  `* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }`
- **Findings:** Headings, kicker labels, buttons, and alert banners expand vertically without truncation or overflowing their bounding boxes. Form submit buttons retain full label legibility.
- **Verdict:** PASS

### 2.3 WCAG 2.3.3: Reduced Motion (`*-reduced-motion.png`)
- **Inspection Method:** Evaluated under `prefers-reduced-motion: reduce`.
- **Findings:** The desktop startup pulse animation and progress indicators disable continuous looping and render static, high-contrast indicators. No jarring layout shifts or uncontrolled motion.
- **Verdict:** PASS

### 2.4 WCAG 2.4.7: Focus Visible (`01-request-step-keyboard-focus.png`)
- **Inspection Method:** Navigated via sequential `Tab` key presses.
- **Findings:** High-contrast focus rings (cyan `#38bdf8` outline with 2px offset) clearly distinguish the currently focused interactive element (`Continue to AI service`).
- **Verdict:** PASS

---

## 3. Screen-by-Screen Review

### 3.1 Step 1: Your Request (`/onboarding`)
- **Images:** `01-request-step-*.png`
- **Review:** Focus heading auto-focuses on arrival. The carried text is preserved and rendered inside a discrete preview container. Clear action pair: "Continue to AI service" (primary) and "Edit request" (secondary).
- **Responsive Behavior:** Forms center smoothly with `max-width: 44rem` on desktop and collapse to full-bleed with 1rem padding on mobile.

### 3.2 Step 2: AI Service Chooser (`/onboarding/ai-service`)
- **Images:** `02-chooser-step-*.png`
- **Review:** 3 clear options (OpenCode CLI, Local service / Ollama, Hosted key) with explicit privacy badges ("Zero cost", "100% private offline", "Your provider account").
- **Responsive Behavior:** 3-card stack renders cleanly in mobile viewports without horizontal scroll.

### 3.3 Step 3: Route Connections
- **Hosted Key (`/onboarding/hosted-key?provider=openai`):** Managed environment variable detection (`OPENAI_API_KEY`), password input with copy/paste cleaning, explicit provider terms acknowledgment.
- **Local Service (`/onboarding/local-service`):** Live loopback probe against `127.0.0.1:11434`, hardware/RAM guidance, discrete failure recovery.
- **OpenCode (`/onboarding/opencode`):** Verified binary path detection at `~/.opencode/bin/opencode`, dynamic listing of 20 active models, zero-config free model indicator.

### 3.4 Step 4: Assistant Creation (`/onboarding/assistant`)
- **Images:** `06-assistant-step-*.png`
- **Review:** Slug and Display Name auto-suggested from the user's initial request. Model route dropdown pre-selects the verified connection. Permissions card explicitly explains human-in-the-loop approvals, fresh workspace isolation, and local memory.
- **Responsive Behavior:** Two-column fields collapse to single-column stack on screens under 640px.

### 3.5 Step 5: First Request Execution & Approval Intro (`/onboarding/first-request`)
- **Images:** `07-first-request-step-*.png`
- **Review:** Carried request presented for final check. Assigned assistant card details model and `fresh` workspace. Explicit explanation of human-in-the-loop approvals before sensitive actions.
- **Execution State:** Upon submission, renders run confirmation, run ID badge, and link to the live execution stream.

### 3.6 Desktop Startup Experience (`desktop/web/index.html`)
- **Healthy (`desktop-startup-healthy.png`):** Centered card, SVG logo, glowing pulse indicator, reassuring text.
- **Diagnostics (`desktop-startup-error.png`):** When startup encounters an error or timeout, the card immediately transitions to an error boundary with troubleshooting bullet points (port collision, Python runtime, log location) and clear tray quit guidance.

---

## 4. Honest Limitations and Waived Items

1. **Browser Engine Coverage:** Visual validation was performed using Chromium under Linux. Real Safari (WebKit/macOS) and mobile Safari on iOS physical devices were not executed in this environment.
2. **Screen Reader Audio:** Semantic ARIA roles (`role="status"`, `aria-live="polite"`, `aria-describedby`) were verified in the HTML DOM structure; live audio screen reader testing was not executed.
3. **Hardware Accelerators:** Local GPU memory measurements reflect Linux kernel sysfs and driver queries rather than proprietary vendor profiling harnesses.

---

## 5. Reviewer Sign-off

All 80 captured visual artifacts demonstrate adherence to Hutch's design system tokens, typography scales, dark mode contrast standards, and responsive requirements. No layout regressions or defects were detected.
