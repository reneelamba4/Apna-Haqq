Paste everything below this line into Claude Code, in the Apna-Haqq project folder:

---

I'm building Apna Haqq, a WhatsApp bot (Flask + Twilio) that tells Indian citizens which government welfare schemes they're eligible for. The repo has:

- `app.py` — the current bot. It has a `FLOW` list (the question steps: language, age, gender, income, ration card, bank account, occupation, marital status) and a `match(profile)` function that returns eligible schemes. Right now `match()` is hardcoded Python if-statements covering only ~13 Maharashtra schemes. 12 languages are wired into `FLOW` already (English, Marathi, Hindi, Gujarati, Bengali, Tamil, Telugu, Kannada, Malayalam, Odia, Assamese, Punjabi) but `match()` ignores state entirely and only knows Maharashtra.
- `schemes_database_raw.json` — 2,163 government schemes across every Indian state/UT plus central schemes, pulled from myScheme.gov.in and individually fact-checked over several research sessions. Each record has: `slug`, `title`, `meta_raw` (scraped description), `state_guess`, `level` (state vs central_or_general), `sections` (list of {heading, content} — this is where benefit amounts and eligibility text live, but it's prose, not structured fields), `risk_flags`, and a `verification` object with `status` (verified / needs_review / plausible_unconfirmed / discontinued), `note` (what was actually checked and any correction), `amount`, `sources`, `checked` (date).
- `schemes_audit.md` — human-readable log of what was found state by state, useful for context on data quality but not needed by the code.

**Important: the JSON does NOT have machine-readable eligibility rules (no `min_age`, `max_income` fields etc.) — eligibility criteria are buried in prose inside `sections` and `verification.note`.** So before you can build a rules engine, you need to design a structured eligibility schema and extract each scheme's actual eligibility criteria into it. Don't assume this data is rules-ready.

What I need built:

1. **Design a structured eligibility schema** — fields like state (or "central"/"any"), min_age, max_age, gender, max_income, ration_card_types, occupation, marital_status, caste_category, disability_required, disability_percent_min, land_ownership_required, worker_board_registration_required, etc. Not every scheme will use every field — most fields should be nullable/optional (absence = not a criterion for that scheme).

2. **Extract eligibility criteria from the existing JSON into that schema.** Start with the ~833 records where `verification.status == "verified"` — those have the most reliable underlying facts. Leave `needs_review` and `plausible_unconfirmed` records for a later pass (flag them, don't try to encode confident eligibility rules from data that's already flagged as uncertain). You can use an LLM call (or your own reasoning) to parse each record's `sections`/`meta_raw`/`verification.note` text into the structured schema — this will take real judgment per-scheme, not a regex.

3. **De-duplicate scraping artifacts first** — many slugs have `(1)`/`(2)` suffixes (e.g. `fapllf` and `fapllf(1)`) that are the same scheme scraped twice, already marked `discontinued` with a note like "duplicate scraping artifact." Drop these before doing the eligibility extraction so you don't do the work twice.

4. **Rewrite `match(profile)`** to be JSON/schema-driven: given a user's profile (age, gender, income, ration card, occupation, marital status, state, and any new fields you add), loop through the structured eligibility data and return every scheme where the user's profile satisfies all of that scheme's non-null criteria.

5. **Add "state of residence" as a new question in `FLOW`**, asked early (right after language, since it determines which language even makes sense to keep offering — e.g. only show Punjabi as a language option or ask state first, your call on ordering). This is currently completely missing — the bot has no idea what state a user is in, so it can't possibly know which state schemes apply.

6. **Add whatever new profile questions the schema needs** that `FLOW` doesn't currently ask — most likely caste category (General/OBC/SC/ST), disability status + percentage, land ownership (for farmer schemes), and construction/unorganized-worker board registration status (this comes up constantly across states' BOCW-board schemes). Keep the flow as short as you can — don't ask a question unless enough schemes actually key off it to justify the extra step for the user.

7. **Keep the multi-language structure intact** — every new question needs entries for all 12 languages in `FLOW`, following the exact pattern already used for the existing questions (a dict keyed by language code: "en", "mr", "hi", "gu", "bn", "ta", "te", "kn", "ml", "or", "as", "pa"). Machine-translate placeholders are fine for now, matching the existing "not yet reviewed by native speakers" caveat already in the code comments — don't hold up the rewrite waiting for native-speaker review.

8. **Preserve the eKYC/renewal/caveat notes already in the existing 13 Maharashtra scheme entries in `match()`** — several of them have hard-won corrections (e.g. Ladki Bahin Yojana's mandatory annual eKYC, PM Ujjwala's actual refill subsidy terms) that came from real fact-checking, not just eligibility gating. Make sure whatever replaces `match()` still surfaces that kind of caveat text alongside the benefit amount, not just a scheme name and rupee figure.

9. Once this is working, run it against a handful of test profiles spanning different states and confirm it returns sensible results before we talk about deploying it.

Start by proposing the structured eligibility schema and showing me a plan for the extraction step before you start writing extraction code for all 833 records — I want to sanity-check the schema first since it's the foundation everything else builds on.
