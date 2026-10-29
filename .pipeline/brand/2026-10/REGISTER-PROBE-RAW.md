# REGISTER-PROBE-RAW - headless-browser probe (2026-10-28 PT)

Raw evidence log. Retrieval date for every entry below: 2026-10-28 (America/Vancouver, PT).
Tool: headless Chromium (Playwright), user agent
`Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36`,
locale en-US, default context. Pages read as rendered DOM text (`innerText("body")`), no logins, no
CAPTCHA solving, no accounts. Pre-screen evidence only; no conclusions about infringement,
registrability, availability or clearance are drawn here or should be drawn from this file.

Notation: "reached" = the page rendered substantive content that was read. "unreachable" = blocked,
gated, or rendered no record content. Tab-separated cells in the source pages are rendered below as a
single space between the code and its title.

---

## 1. WIPO - Vienna Classification (International Classification of the Figurative Elements of Marks)

### 1.1 Edition actually displayed

Reached by browsing: WIPO landing page -> "Access the Vienna Classification Publication" -> publication
index -> Division 26 frame. Two independent pages display the edition string.

- `https://nivilo.wipo.int/vienna.htm` - HTTP 200, title "Vienna Classification Publication".
  Displayed edition string, verbatim:

```text
INTERNATIONAL CLASSIFICATION OF THE FIGURATIVE ELEMENTS OF MARKS
under the
Vienna Agreement
Tenth Edition	CLASSIFICATION INTERNATIONALE DES ÉLÉMENTS FIGURATIFS DES MARQUES
établie en vertu de
l'Arrangement de Vienne
Dixième édition


In force as from January 1, 2026
to December 31, 2028
```

- `https://nivilo.wipo.int/vienna10/index.htm?lang=EN` - HTTP 200, title "Vienna Classification".
  Header displayed: `INTERNATIONAL CLASSIFICATION OF THE FIGURATIVE ELEMENTS OF MARKS / under the
  Vienna Agreement / Tenth Edition`.
- Landing pages consulted (browse entry points):
  - `https://www.wipo.int/classifications/vienna/en/` -> HTTP 200, HTML meta-refresh to
    `https://www.wipo.int/es/web/classification-vienna` (Spanish locale).
  - `https://www.wipo.int/en/web/classification-vienna` - HTTP 200, title "Vienna Classification".
    Verbatim: "VCL10: files and data (entry into force on 1 January 2026)". Page also links
    "Access the Vienna Classification Publication".
  - `https://www.wipo.int/vienna/en/` - HTTP 404 ("Page Not Found - WIPO | 404").
  - `https://vienna.wipo.int/` - DNS failure (getaddrinfo ENOTFOUND); no such host.
  - VCL10 reference files (not opened): `https://www.wipo.int/classifications/vienna/es/ITsupport/Version20260101/index.html`.

Edition recorded as displayed: "Tenth Edition", "In force as from January 1, 2026 to December 31, 2028".

### 1.2 Code + verbatim definition: polygon outline

Reached by browse to the Division 26 frame of the Tenth Edition publication:
`https://nivilo.wipo.int/vienna10/divrender.htm?xml=xml/en/full.xml&xsl=xslt/addmode.xsl&cxsl=xslt/vienna8.xsl&mode=full&index=26&lang=EN&hash=id26`
(HTTP 200; same text below also present in the publication's XML source
`https://nivilo.wipo.int/vienna10/xml/en/full.xml`, 190,737 bytes, which was downloaded and read as a
cross-check). Verbatim as rendered:

```text
Category 26	GEOMETRICAL FIGURES AND SOLIDS

Notes:	(a)	Including geometrical figures and solids composed of human beings, animals, plants or objects.
	(b)	Not including inscriptions forming geometrical figures, which are classified in division 27.1.

	26.5	OTHER POLYGONS
	Note:	Not including elongated polygons (25.3.1).

	*	26.5.1	One polygon
	*	26.5.2	Two polygons, one inside the other (except 26.5.10 and 26.5.11)
	*	26.5.3	Several polygons, inside one another (except 26.5.10 and 26.5.11)
	*	26.5.4	Several polygons, juxtaposed, joined or intersecting
	*	26.5.8	Polygons with one or more truncated or rounded angles
	*	26.5.9	Polygons containing one or more circles or ellipses
	*	26.5.10	Polygons containing one or more triangles or lines forming an angle
	*	26.5.11	Polygons containing one or more quadrilaterals
	*	26.5.12	Polygons containing one or more other geometrical figures
	Note:	Including polygons containing bent or straight lines (except 26.5.10).
	*	26.5.26	Polygons with cutout areas

	Auxiliary Sections of Division 26.5
	(associated with Principal Sections 26.5.1-26.5.4, 26.5.8-26.5.12, 26.5.26)
	A	26.5.6	Polygonal figures with one or more convex or concave sides
	A	26.5.13	Polygons containing representations of heavenly bodies or natural phenomena
	A	26.5.14	Polygons containing representations of human beings or parts of the human body
	A	26.5.15	Polygons containing representations of animals, parts of animals' bodies or plants
	A	26.5.16	Polygons containing other figurative elements
	A	26.5.17	Polygons containing one or more numerals
	A	26.5.18	Polygons containing one or more letters
	A	26.5.19	Polygons with inscriptions projecting beyond the circumference
	A	26.5.22	Polygons containing other inscriptions
	A	26.5.24	Polygons with dark surfaces or parts of surfaces
```

Also rendered in Category 26 and relevant to a triangle-outline reading (division 26.3):

```text
	26.3	TRIANGLES, LINES FORMING AN ANGLE
	*	26.3.1	One triangle
	*	26.3.2	Two triangles, one inside the other
	*	26.3.3	More than two triangles, inside one another
	*	26.3.4	Several triangles, juxtaposed, joined or intersecting
	*	26.3.10	Triangles containing one or more circles, ellipses or polygons (except 26.3.11)
	*	26.3.11	Triangles containing one or more quadrilaterals
	*	26.3.12	Triangles containing one or more other geometrical figures
	*	26.3.26	Triangles with cutout areas
```

Source URL for the two blocks above:
`https://nivilo.wipo.int/vienna10/divrender.htm?xml=xml/en/full.xml&xsl=xslt/addmode.xsl&cxsl=xslt/vienna8.xsl&mode=full&index=26&lang=EN&hash=id26`

### 1.3 Code + verbatim definition: centred dot / small circle

Same Division 26 frame, group 26.1 (a dot is not itself given a dedicated Vienna division; the entries
below are the ones the Tenth Edition defines for circles/ellipses). Verbatim as rendered:

```text
	26.1	CIRCLES, ELLIPSES
	*	26.1.1	Circles
	*	26.1.2	Ellipses
	*	26.1.4	Two circles, two ellipses, one inside the other
	*	26.1.5	More than two circles or ellipses, inside one another, spirals
	*	26.1.6	Several circles or ellipses, juxtaposed, tangential or intersecting
	*	26.1.7	Circles containing one or more ellipses
	*	26.1.8	Circles containing one or more polygons (except 26.1.10 and 26.1.11)
	*	26.1.9	Ellipses containing one or more circles or polygons (except 26.1.10 and 26.1.11)
	*	26.1.10	Circles or ellipses containing one or more triangles or lines forming an angle
	*	26.1.11	Circles or ellipses containing one or more quadrilaterals
	*	26.1.12	Circles or ellipses containing one or more other geometrical figures
	Note:	Including circles or ellipses containing bent or straight lines (except 26.1.10).
	*	26.1.26	Circles or ellipses with cutout areas

	Auxiliary Sections of Division 26.1
	Auxiliary Section Associated with Principal Sections 26.1.1, 26.1.2, 26.1.8-26.1.12, 26.1.26
	A	26.1.3	One circle or ellipse
	Auxiliary Sections Associated with Principal Sections 26.1.1, 26.1.2, 26.1.4-26.1.12, 26.1.26
	A	26.1.13	Circles or ellipses containing representations of heavenly bodies or natural phenomena
	A	26.1.14	Circles or ellipses containing representations of human beings or parts of the human body
	A	26.1.15	Circles or ellipses containing representations of animals, parts of animals' bodies or plants
	A	26.1.16	Circles or ellipses containing other figurative elements
	A	26.1.17	Circles or ellipses containing one or more numerals
	A	26.1.18	Circles or ellipses containing one or more letters
	A	26.1.19	Circles or ellipses with inscriptions projecting beyond the circumference
	A	26.1.20	Circles or ellipses containing inscriptions arranged along the radius or diameter
	A	26.1.21	Circles or ellipses containing inscriptions arranged in circular or elliptical form
	A	26.1.22	Circles or ellipses containing inscriptions arranged in some other form
	A	26.1.24	Circles or ellipses with dark surfaces or parts of surfaces
	Auxiliary Section Associated with Principal Sections 26.1.1, 26.1.2
	A	26.1.25	Circles or ellipses representing a halo
```

Source URL: same Division 26 frame URL as 1.2.

### 1.4 Scope note on section 1

The blocks above are transcription only. Which code or codes an application would actually carry for a
given device is an examiner/classification act. Nothing here asserts that any code applies to any HUTCH
asset; the definitions are recorded so a human can compare them against the device. The publication's
own "Search" control (in the index frame) was not exercised; these entries were reached by browse and
by the publication's XML source, not by the search UI. The separate "Vienna Classification Assistant"
(`https://www3.wipo.int/bnd-api/vienna-classification-assistant/`, linked from the WIPO landing page)
was not opened.

---

## 2. USPTO - TSDR / trademark search

### 2.1 Serial 99695333 via TSDR

- URL: `https://tsdr.uspto.gov/#caseNumber=99695333&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch`
- Outcome: HTTP 200; rendered title "Trademark Status & Document Retrieval". The page rendered only
  site navigation and the search form shell; no case data (mark, owner, status, classes, goods or
  dates) was rendered for the serial after a 5 s wait. Status: record NOT obtained - unreachable via
  this route.
- Visible text on the page, verbatim (includes the current TSDR availability notice):

```text
For assistance with TSDR, email <a href="mailto:teas@uspto.gov">teas@uspto.gov</a> and include your serial number, the document you are looking for, and a screenshot of any error messages you have received.

October 22 update: To address recent availability issues caused by excessive data mining, we have implemented some technical adjustments to improve TSDR performance. We are actively monitoring system stability and may implement additional security measures if necessary.
```

### 2.2 Serial 99695333 via TSDR API

- URL: `https://tsdrapi.uspto.gov/ts/cd/casestatus/sn99695333/info`
- Outcome: HTTP 401. Body rendered, verbatim (full page text):

```text
Beginning October 2, you’ll need to register for an API key to download bulk data from our TSDR APIs. Register for an API key at https://account.uspto.gov/api-manager/. Learn more about this new requirement at https://developer.uspto.gov/api-catalog. [000001a105f49446-2f0d999]
```

No API key was requested or used (no accounts, no logins). Serial 87196849 was not separately attempted
against this endpoint after the same key requirement was observed.

### 2.3 USPTO trademark search (tmsearch.uspto.gov)

- `https://tmsearch.uspto.gov/` -> HTTP 200, redirects to `https://tmsearch.uspto.gov/search/search-information`,
  title "Trademark search". Rendered the search shell and help/announcement panels only.
- `https://tmsearch.uspto.gov/search/search-results?query=99695333` -> HTTP 200, title "Trademark search".
  Rendered the filter panels (Status filter: Live 0, Registered, Pending, Dead 0, Cancelled, Abandoned;
  Class filter 001-045) and the literal text `No results found`.
- `https://tmsearch.uspto.gov/search/search-results?q=99695333` -> HTTP 200, same shell, same
  `No results found` text.
- Reading: the query-string form did not execute a serial search. No record content for 99695333 or
  87196849 was obtained; the "No results found" string is recorded as an artifact of the attempted
  query form, NOT as evidence that no filing exists. Status: unreachable for this probe.

No CAPTCHA or Cloudflare challenge text ("captcha", "not a robot", "just a moment", "attention
required") was rendered on any USPTO page in this run.

---

## 3. UKIPO - trade mark records (trademarks.ipo.gov.uk)

All three record pages were reached (HTTP 200, title "Search for a trade mark - Intellectual Property
Office") and read from the rendered Overview, "List of goods and services" and "Names and addresses"
tabs.

### 3.1 UK00003791602

- URL: `https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00003791602`
- Status: Registered
- Trade mark (verbatim): `HUTCH`
- Classes: 9, 35, 39, 42
- Dates (verbatim labels and values): Filing date `24 May 2022`; Date of entry in register `10 February 2023`;
  Renewal date `24 May 2032`
- Owner(s) name (verbatim): `Hutch Logistics Ltd`; address `1 Atholl Road, Chelmer Village, Chelmsford, CM6 2TB, United Kingdom`;
  Country of Incorporation `United Kingdom`. IPO representative `Harper James`.
- Class 9 goods/services, first ~200 characters (truncated, elided by this log):

```text
Logistics software; business management software; warehouse management system software; warehouse management software; customer relation management software; supply chain management software; software in relation to the organisation of the shipping and delivery of goods;
```

- Class 35 goods/services, first ~200 characters (truncated): `Online ordering services; data management; inventory management; commercial business management; inventory management services; inventory control; computerised inventory control; management of business [for others];`

### 3.2 UK00902129492

- URL: `https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00902129492`
- Status: Registered
- Trade mark (verbatim): `HUTCH`
- Classes: 9, 35, 36, 37, 38, 39, 40, 41, 42
- Dates: Filing date `12 March 2001`; Date of entry in register `29 August 2003`; Renewal date `12 March 2031`
- Owner(s) name (verbatim): `Hutchison Whampoa Enterprises (Bahamas) Limited`; address `P.O. Box N-3944, 1st Floor, Building A, Caves Corporate Centre, Blake Road and West Bay Street, Nassau, Bahamas`;
  Country of Incorporation `Bahamas`. IPO representative `Venner Shipley LLP`.
- Class 9 goods/services, first ~200 characters (truncated):

```text
Electric, electronic, facsimile, telex, telephone, telegram, data acquisition installations, apparatus and instruments; all for processing, logging, storing, transmission, display, reception, input, output or print-out of non-pictorial or graphical data; computer software and programmes;
```

- Class 35 goods/services, first ~200 characters (truncated): `Commercial or industrial management assistance; commercial or industrial information agencies; advertising and promotion services and information services relating thereto; rental of advertising space;`

### 3.3 UK00915655715

- URL: `https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00915655715`
- Status: Expired
- Trade mark (verbatim): `RACE KINGS` (this record is not a HUTCH mark; recorded because it was on the attempted list)
- Classes: 9, 41
- Dates: Filing date `13 July 2016`; Date of entry in register `14 July 2017`; Renewal date `13 July 2026`
- Owner(s) name (verbatim): `Hutch Games Ltd`; address `44-46 Scrutton Street, London, EC2A 4HH, United Kingdom`;
  Country of Incorporation `United Kingdom`. IPO representative `Hansel Henson Limited`.
- Class 9 goods/services, complete as rendered:

```text
Games software; games software applications accessible using smart televisions, tablets, mobile phones, smartphones, PCs, games consoles and other communication devices delivered via the Internet and other communications networks; electronic publications and information in connection with games software made available via the Internet and other communications networks (downloadable).
```

### 3.4 Alternative UKIPO URL form tried

- `https://trademarks.ipo.gov.uk/ipo-tmtext/page/Results/1/UK00003791602` -> HTTP 404, rendered
  "Sorry, the page you are looking for cannot be found".
- Same 404 for `.../UK00902129492` and `.../UK00915655715`.

No CAPTCHA gate was encountered on trademarks.ipo.gov.uk in this run (earlier 403 CAPTCHA gate recorded
in IP-CLEARANCE.md was not reproduced).

---

## 4. EUIPO eSearch / TMview

- `https://euipo.europa.eu/eSearch/` and `https://www.tmdn.org/tmview/`: NOT ATTEMPTED. Time budget for
  this probe was exhausted by sections 1-3. No outcome is recorded either way; do not read this as
  reachable or unreachable.

---

## Coverage summary

| Register | Serials / numbers attempted | Reached? | Facts obtained | URL |
|---|---|---|---|---|
| WIPO Vienna (VCL) | n/a (edition + division 26) | reached (browse + XML source) | Edition: Tenth Edition, in force 2026-01-01 to 2028-12-31. Verbatim definitions for 26.5 OTHER POLYGONS, 26.5.1-26.5.26, 26.5.6/26.5.24 and 26.3 TRIANGLES set; and 26.1 CIRCLES, ELLIPSES, 26.1.1, 26.1.3, 26.1.24 | https://nivilo.wipo.int/vienna10/index.htm?lang=EN ; https://nivilo.wipo.int/vienna.htm |
| USPTO TSDR | 99695333 (87196849 not separately retried) | NOT reached | none - page shell only; API returns HTTP 401 API-key notice | https://tsdr.uspto.gov/#caseNumber=99695333&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch |
| USPTO tsdrapi | sn99695333 | NOT reached (HTTP 401) | API-key requirement text only | https://tsdrapi.uspto.gov/ts/cd/casestatus/sn99695333/info |
| USPTO tmsearch | 99695333 (both query forms) | NOT reached | none - shell plus "No results found" artifact | https://tmsearch.uspto.gov/search/search-results?query=99695333 |
| UKIPO | UK00003791602 | reached | HUTCH; Registered; cl. 9/35/39/42; Hutch Logistics Ltd; filed 2022-05-24, registered 2023-02-10, renewal 2032-05-24 | https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00003791602 |
| UKIPO | UK00902129492 | reached | HUTCH; Registered; cl. 9/35/36/37/38/39/40/41/42; Hutchison Whampoa Enterprises (Bahamas) Limited; filed 2001-03-12, registered 2003-08-29, renewal 2031-03-12 | https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00902129492 |
| UKIPO | UK00915655715 | reached | RACE KINGS (not HUTCH); Expired; cl. 9/41; Hutch Games Ltd; filed 2016-07-13, registered 2017-07-14, renewal 2026-07-13 | https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00915655715 |
| UKIPO (alt path) | all three | NOT reached | HTTP 404 for /ipo-tmtext/ form | https://trademarks.ipo.gov.uk/ipo-tmtext/page/Results/1/UK00003791602 |
| EUIPO eSearch / TMview | - | NOT ATTEMPTED | none | https://euipo.europa.eu/eSearch/ ; https://www.tmdn.org/tmview/ |

Open items for a human, recorded only as gaps: (a) USPTO serials 99695333 and 87196849 remain
unretrieved from an official source - TSDR needs a browser session that can complete its own search
submission, or an API key; (b) no Vienna code has been assigned to any HUTCH asset - definitions are
transcribed, mapping is not asserted; (c) EUIPO/TMview unattempted.

Pre-screen only, not clearance; blocked = unreachable.
