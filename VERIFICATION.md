# Version 2.4 verification — November 10, 2026 (America/Chicago)

- 82 backend/updater tests passed. New tests cover JSON-LD JobPosting/graph extraction, HTML-entity descriptions, main/article fallback, navigation/form/script exclusion, ambiguous pages, unavailable text, invalid URLs, private/mixed DNS answers, pinned-IP TLS hostname handling, redirects, 403s, non-HTML and oversized pages, authentication/origin checks and no persistence on fetch.
- Browser preview verified the URL-first import dialog, alphabetical source menu, Fetch job details action, 8,047-character description fill and explicit review-before-save status. The preview API used extraction output from a real public Greenhouse page; workspace jobs remained synthetic and no import/application was submitted.
- Live HTML was retrieved through the environment's standard HTTPS proxy and parsed successfully. The deployment transport deliberately rejects this environment's private DNS mapping, so direct pinned-connection fetching still needs a homelab smoke test. No transport security check was bypassed.
- Existing 19 date/statistics and 15 extension checks pass; Python and JavaScript syntax checks pass. No new runtime dependencies.
- Homelab deployment remains pending. Existing .env, including the Brave API key and encryption key, and the persistent data volume are preserved by the updater.

# Version 2.3 verification — November 9, 2026 (America/Chicago)

- 52 backend/updater tests passed. New checks cover all 100 image entries, no duplicate IDs, preservation of earlier extras, every source having an application review, successful feed configurations, RSS/JSON attribution, company-specific Ashby identity, Greenhouse board-token mapping and Lever read-only parsing.
- All 100 catalog URLs received availability checks, with failures retained. Three stale links received verified replacements. Full records are packaged in radar/assets/source_review.json.
- All 29 public feed/API collectors returned listings in live read-only smoke checks. All 18 sampled Greenhouse forms passed the framing check; sampled Ashby forms stayed external. See radar/assets/collection_review.json.
- Browser preview showed 106 source cards, searched Figma to one visible card, and showed source/application modes and image numbering. Refresh no longer interrupts an active source filter. Preview workspace jobs were synthetic.
- Existing 19 statistics/date and 15 extension matching checks pass. Python compilation and JavaScript syntax pass.
- No employer applications, applicant data, documents, consents or CAPTCHA responses were submitted during checks. No paid indexed-search key was tested. Homelab installation and production-origin checks remain pending.

# Version 2.2 verification — November 9, 2026 (America/Chicago)

- 46 backend/updater tests passed, including URL validation, source attribution, all-source audit coverage, framing restrictions, redirects, content types, authenticated apply options and no accidental application records.
- Existing 19 statistics/date and 15 extension checks pass. Python compilation and JavaScript syntax pass.
- Live read-only checks accepted sample Greenhouse forms for Canonical, Cloudflare and GitLab; Ashby's own sample was blocked by X-Frame-Options DENY.
- Browser preview displayed a real public Cloudflare form and attachments in the sandboxed panel. Checking/loading left local status New. Manual confirmation filled Applied and today's editable date, with Save application still required. Fixture metadata was synthetic. No employer form fields, uploads, consents, CAPTCHA or submissions were completed.
- Provider findings and limitations are recorded in APPLICATION_SOURCES.md. Homelab deployment and production-origin form checks remain pending.

# Version 2.1 verification — November 10, 2026

- 20 backend/updater tests passed, including new source registration, Ashby field mapping, Greenhouse domain validation, applied date editing, private-data preservation and code backups.
- 19 statistics/date checks and 15 existing form-answer matching checks passed.
- Browser preview verified search pending/completion states, eight filtered results, date autofill and manual date persistence, 14/30-day controls, footer target and non-overlapping search fields at a 1363px viewport. Preview records were synthetic, not the live workspace.
- Official Ashby public API returned 76 listed openings during a live smoke check. Indexed providers were tested with simulated responses; no paid Brave API key was used.
- Docker rebuild and deployment on the homelab have not been performed in this environment.

# Verification record

Verified on November 9 2026 in a clean Python 3.12 virtual environment using the packaged runtime dependency lock.

- 14 backend tests passed: authentication and request origin checks, encrypted uploads and notes, original-file retrieval, factual tailoring, keyword gaps, independent draft versions, DOCX/PDF/TXT exports, sensitive profile exclusion, unsupported URL rejection, application retention, follow-up dates, due-letter deduplication, source-failure retention, changed-query caching, legacy import, Dice schema parsing and indexed-search domain checks.
- 15 form-answer matching checks passed, including ambiguous questions, negated authorization, duplicate answers, historical disability questions, consent statements, conditional conviction questions and compound citizenship wording.
- Cloudflare Access verification tests reject wrong audience, wrong email, expired JWTs, invalid signatures and spoofed email headers. Unconfigured production Access fails closed.
- Python compilation, JavaScript syntax checks, and shell syntax checks passed.
- Tunnel helper checks verified existing-route preservation, placement before the catch-all, timestamped backup creation, and refusal of duplicate routes.
- DOCX and PDF exports of a synthetic resume were rendered and visually inspected. The Word title border was removed after inspection. Export text remains selectable and the layout uses one column.
- Dice live MCP search returned 50 listings with source and company links. Its summary results remain unverified for tailoring until a full description is loaded or imported.
- ZipRecruiter MCP returned HTTP 403 during verification. Its status is not represented as a successful connection. Optional Brave discovery requires an owner-supplied API key and was tested with simulated responses, not a live paid key.
- The included migration JSON contains 355 jobs from the earlier workspace snapshot and zero application records.

## Verification still needed on the homelab

A Docker engine was unavailable in the build environment, so the Docker image and Compose deployment were not executed here. The clean Python installation and backend tests passed instead. Version 2.1 browser checks used a local synthetic-data preview; live homelab authentication and deployment still require verification.

The package has not been deployed to the Ubuntu VM or connected to the live Cloudflare hostname. Validate container startup, persistent data, Google authentication, an unauthorized browser challenge, tunnel routing, source access, extension behavior on actual forms, and file downloads after installation. The existing ChatGPT-hosted version is separate and was not replaced.
