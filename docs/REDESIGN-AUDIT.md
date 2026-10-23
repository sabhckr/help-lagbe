# Help Lagbe? — redesign audit (23 October 2026)

Scope: the live site at https://help-lagbe-eight.vercel.app/ (read-only checks), the repository at commit `9322729`, and the code paths for reporting, tracking, support, publication and staff tools. Measurements were taken from the live pages (word counts, form fields) on 23 October 2026.

## 1. Deployment finding (read first)

Pushing `main` (commit `9322729`) also deployed it to the live Vercel site. The live site now serves this build. Read-only checks show:

- Production configuration is active (HSTS header present, no debugger output on errors).
- `/healthz` returns `ok`. Demo seeding only runs in development, so the demo staff accounts should not exist on the live site. This was not tested by logging in.
- The database behind the live site is not confirmed. A SQLite file cannot hold writes on Vercel's serverless filesystem, so `DATABASE_URL` and the storage plan need checking before any real report is accepted.

Decision needed from the owner: keep, roll back or pause the live deployment, and turn off automatic deploys if a push should not go live. This work does not deploy anything.

## 2. What the live site does today

| Page | Words (approx.) | Inputs | Finding |
|---|---|---|---|
| Home | 308 | 0 | Three hero buttons plus four pillar cards repeat the same actions. Support status, helplines and "latest" all sit on one page. |
| Report | 545 | 25 | One long page. Identity, evidence and consent appear together. The immediate-danger question is buried mid-form. No review step, no saved draft. |
| Live Human Support | 381 | 0 | Honest that no agent is online, but the text is long and the page is named "live" while mostly closed. |
| Legal Help | 353 | 0 | Long explanatory text, no action the reader can take. |
| Public Awareness | 165 | 0 | Thin page that duplicates Stories. |
| Investigations | 201 | 0 | Thin page that duplicates Stories. |

Other live findings:

- Seventeen public pages behind a six-item header plus a "More" menu. Several pages say nearly the same thing (Get Help, Report Wrongdoing, Live Support, Safety, Safeguarding).
- The default language is English. Bangla is a switch, not the default, although the brief is Bangla-first.
- The emergency-contacts box on the report and home pages says no numbers are verified. On a safety page this is a dead end. Official national numbers (999 and 109) are confirmed by several public outlets; 1098 has only one weak source and must be checked before it is shown.
- The palette is charcoal, ivory and teal. The brief asks for ivory, burgundy, muted teal and soft coral.
- There is no illustration system. The only images are icons and a logo.
- Reporters see internal workflow words (Triage, Specialist review, Referral/action) on their tracking page.

## 3. Code findings

| # | Severity | Finding | Evidence |
|---|---|---|---|
| 1 | High | The receipt, including the one-time tracking key, is stored in the signed session cookie. Flask signs cookies but does not encrypt them. | `app/routes/report.py`: `session["report_receipt"] = {"reference", "secret"}` |
| 2 | High | The visitor chat token sits in the session cookie. It grants access to a private conversation. | `app/routes/support.py`: `session["support"] = {"reference", "token"}` |
| 3 | High | Production data location is unconfirmed; SQLite on serverless storage would lose or refuse writes. | Vercel deployment; no `vercel.json`; `DATABASE_URL` not confirmed |
| 4 | Medium | Language switching drops typed text because nothing is saved until the form is submitted. | `set_language` redirects; no draft storage |
| 5 | Medium | The brief needs one submit with a confirmed reference, but a double click can create a second case. | `POST /report/new` creates a case on every submit |
| 6 | Medium | Evidence uploads only happen with the final submit: no progress, no removal, and no validation feedback before submit. | Single multipart form |
| 7 | Medium | Public category list shows 15 internal categories, several of which overlap. | `app/permissions.py` `CATEGORY_DEPARTMENT` |
| 8 | Medium | Public status vocabulary has 11 internal states and no "more information needed" state. | `app/models/case.py` `STATUSES` |
| 9 | Low | Bangla translations and public content are unreviewed; the English and Bangla text does not match in tone everywhere. | `app/translations/bn/*.json`, `app/templates/public/content/*` |

Things that work and are kept: password sign-in with lockout, staff TOTP enrolment and verification, anonymous and confidential reporting at the data layer, the encrypted identity store with reason-gated unlock, need-to-know case access, evidence hashing and custody records, the publication gates with two-person rules, the support queue with honest availability, the audit trail, and the 97 tests.

## 4. Decisions

Keep (functional): authentication and MFA; case, identity, evidence, publication and support services; staff workspaces (restyled, not rewritten); the audit trail.

Simplify:

- Public site from seventeen pages to seven: Home, Get help, Report, My case, Stories, About, Safety. Privacy, Contact and Accessibility sit in the footer.
- Home page: one hero, three actions, support status, a helplines strip and the latest published stories. Nothing else.
- Report: six short steps with autosaved drafts (see section 5).
- Categories from 15 to 8 user-facing groups. Staff routing is kept.
- Public statuses from 11 to 5 user-facing states: Received, Under review, More information needed, Referred (only when a referral exists), Closed.
- Default language Bangla, with complete English.

Remove or merge:

- Pages: Report Wrongdoing, Live Support, Legal Help, Digital Safety, Safeguarding, Awareness, Investigations, Editorial Policy, Corrections, Complaints, Accessibility. Their content moves into Get help, Safety, About, Stories and Contact. Old URLs redirect to the new pages.
- The "More" dropdown.
- The "live chat" label when no agent is present. The honest state is "No one is available right now", with alternatives.
- The empty "no verified numbers" box as the only safety content.

Fix:

- Keep the one-time key out of cookies: encrypted draft and receipt storage on the server, cleared on dismissal.
- Autosave step text in the browser (sessionStorage) so language switching preserves progress.
- Single-submit with a server-side guard so a double click cannot create two cases.
- Evidence step: visible progress, per-file removal and immediate type and size errors.

Do not change: the database schema beyond additive changes; production data (none is touched); the integration contracts (none exist outside the app).

## 5. Reporting design

Six steps, one question per screen:

1. What happened? Eight categories with plain examples.
2. Is anyone in danger right now? Yes, not sure or no. Yes shows official numbers and the honest statement that this site does not call emergency services.
3. What happened? One large text area with optional prompts for what, when and where. A warning not to share passwords or banking details.
4. How do you want to report? Anonymous or confidential, explained in plain words with who can see what. Contact options only when confidential.
5. Evidence (optional): up to five files, with type and size checks, progress and removal.
6. Review, edit and submit once. The reference and one-time key are shown only after the database confirms the case.

Each step saves to an encrypted server-side draft tied to the browser session. The draft expires after 24 hours and is deleted once the report is submitted.

## 6. Accessibility and layout targets

Widths: 320, 360, 390, 768, 1024 and 1440 px, with no horizontal scrolling. Touch targets at least 44 px. Visible focus. A skip link. Live regions for status messages. Reduced-motion support. Contrast checked for every colour pair in the palette. Bengali set in Noto Sans Bengali.

## 7. Results (23 October 2026)

### Removed or merged

| Before | After |
|---|---|
| 17 public pages and a "More" menu | 7 pages in the menu (Home, Get help, Report, My case, Stories, About) plus Safety, Privacy and Contact in the footer |
| Get Help, Report Wrongdoing, Live Support, Legal Help, Digital Safety | Get help (one page with Now, Talk, Report and Information sections) and Safety |
| Awareness, Investigations, Corrections | Stories (published pieces, label meanings and the corrections log) |
| Safeguarding, Editorial Policy | About |
| Complaints, Accessibility | Contact |
| Long English content fragments (30 files) | Short Bangla-first copy in `app/translations/{bn,en}/public.json` |
| 15 internal report categories | 8 plain categories (migration `f8e40f3bb73c` maps old values) |
| 11 statuses shown to reporters | 5 public states: Received, Under review, More information needed, Referred, Closed (a real `needs_information` status was added for staff) |

Old addresses redirect permanently to their new pages.

### Redesigned

- **Home:** one heading, three actions ("সাহায্য চাই", "অভিযোগ জানান", "কারও সঙ্গে কথা বলুন"), the national helplines with their source, an honest support status and at most three published stories.
- **Report:** six steps, one question each, with a progress bar. Answers are saved to an encrypted server draft at each step and autosaved in the browser tab, so a language switch keeps typed text. Uploads are checked, encrypted, removable and moved into the case on submit. The final submit claims the draft atomically, so a double click creates one case. The reference and key are shown only after the database commit.
- **Receipt:** the key is no longer stored in the session cookie. It lives encrypted in the draft until "I have saved" or two hours.
- **Tracking:** shows only the five public states, the team's messages and verified outcomes. No internal notes, severity or workflow words.
- **Talk to someone:** the chat form appears only when the support desk is staffed and an agent is present. Otherwise the page says "No one is available right now" and offers the report and tracking.
- **Design system:** the requested palette (ivory, burgundy, muted teal, soft coral, charcoal), with one darker control border to meet 3:1. Noto Sans Bengali body, Noto Serif Bengali headings, 48 px touch targets, visible 3 px focus, reduced-motion support.
- **Illustrations:** eight SVG files in `app/static/art/`: support-hands, two-talking, private-report, privacy-shield, calm-empty, report-received, agent-support, safety-guidance. Each is under 1.1 KB, has a `<title>`, and is shown with empty alt text where it is decorative.

### Verification

| Check | Result |
|---|---|
| `scripts/check.sh` (ruff, ruff format, mypy on 49 files, bandit, pip-audit, pytest, compile, template load, production config) | all passed; 115 tests |
| Render sweep: public pages in both languages, about 25 staff pages for each of nine roles in both languages | 0 server errors |
| Headless Chrome (Playwright): 15 pages at 320, 360, 390, 768, 1024 and 1440 px, Bangla and English | no horizontal overflow; no touch target under 40 px; no console errors |
| Keyboard | first Tab reaches the skip link; focus outline 3 px solid |
| Reduced motion | transitions are 0 s |
| Phone menu | opens, reports `aria-expanded`, closes with Escape |
| Report walk-through at 360 px in Bangla with a language switch at step 3 | unsaved text kept; identity fields toggle; double-click submit created one case |
| Service worker | registers in Chrome; fails only inside the app's built-in browser pane |

### Not verified

- Screen readers (TalkBack, VoiceOver) were not run.
- No real low-end Android phone or throttled network was tested.
- The Bangla text was written by the assistant and has not been reviewed by a native editor.
- The 999 and 109 sources are news and directory pages, not government pages. 1098 is not shown because no reliable source confirmed it.
