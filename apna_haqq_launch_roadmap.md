# Apna Haqq — Launch Roadmap (sandbox → live in villages)

Last updated: 2026-07-17

## Status flip since this was first written

Track C item 12 (state-by-state scheme verification) is now **fully complete** — all 2,163 schemes across every state, UT, and central program have been individually fact-checked, dated, and sourced in `schemes_audit.md`. 12 languages are live in `app.py` (English, Marathi, Hindi, Gujarati, Bengali, Tamil, Telugu, Kannada, Malayalam, Odia, Assamese, Punjabi). This was the slow, research-heavy half of the project and it's done.

**What that means for priority order now:** the data is no longer the bottleneck — the rules engine is. Track C's item 13 (rewrite `match()` into a generic, JSON-driven, state-aware engine) is now the single most valuable next piece of work, full stop. Everything below is reordered around that.

## Track A — Verification (start TODAY, runs in background, don't block on it)

1. In Twilio console, register your new SIM's number as a WhatsApp Sender / request WhatsApp Business API access. This starts Meta's clock.
2. Buy a domain (if not done) + set up an email on that domain (e.g. hello@apnahaqq.com or similar) — Meta requires domain + matching email for Business verification.
3. Create/verify a Meta Business Manager account. Needs: legal name matching a registration document (Tri City's GST/incorporation docs will work, or register fresh if you want Apna Haqq separate), domain + email above.
4. Draft a one-page privacy policy + terms/disclaimer (plain language: what data you collect — income, disability, marital status, etc. — how long you keep it, that the bot gives informational guidance not guaranteed approval). Needed for Meta verification, and you should have this regardless given the sensitivity of what you're asking people.
5. Submit WhatsApp message templates for approval (needed for anything Twilio-initiates, e.g. a "did this help you?" follow-up) — separate approval queue from #3.

Expect 2–14 days for #3. Keep working on Track B/C while it processes.

## Track B — Get the bot actually running on Railway

6. Resolve GitHub push access (decide: personal access token, or screen-control method) and push current `app.py` to `reneelamba4/Apna-Haqq`.
7. Connect Railway to the GitHub repo, deploy.
8. Move secrets (Twilio Account SID, Auth Token) into Railway environment variables — never hardcode them in app.py.
9. Add a Postgres or Redis add-on on Railway for session storage. Right now sessions live in an in-memory Python dict — Railway restarts/redeploys will wipe every in-progress conversation. This needs fixing before real users touch it.
10. Point the Twilio WhatsApp webhook at your Railway deployment URL.
11. End-to-end test: message the bot yourself in each of the 5 languages currently live (English, Marathi, Hindi, Gujarati, Bengali), confirm no crashes.

## Track C — Finish the core product (the actual eligibility logic)

12. ~~State-by-state scheme verification~~ — **DONE.** All 2,163 schemes verified, sourced, dated. See `schemes_audit.md`. 331 are flagged `needs_review` (real ambiguity, worth a second look before showing to users) and 953 are `plausible_unconfirmed` (mostly small welfare-board line items where an exact figure wasn't locatable) — neither of these blocks launch, they're just lower-confidence than the 833 `verified` records.
13. **Rewrite `match()`** from hardcoded Maharashtra-only logic into a generic rules engine driven by `schemes_database_raw.json` (state + language aware). This is the biggest single engineering lift left in the whole project — best done in Claude Code, not Cowork, since it's a real architecture decision (how do you encode "income <= 2.5L AND age 21-65 AND gender=F" as data instead of Python if-statements for 2,163 schemes with wildly inconsistent eligibility fields?). Suggest starting with the ~833 `verified` records only, expanding to `needs_review`/`plausible_unconfirmed` later.
14. Expand the question flow — right now it only asks the 7 fields Maharashtra's original 13 schemes needed (age, gender, income, ration card, bank account, occupation, marital status). Other states' schemes need caste category, disability status/percentage, land ownership, worker registration status (BOCW-board membership shows up constantly), and state of residence (which isn't asked at all right now — the bot has no way to know which state's schemes to even show someone). State of residence is probably the single most urgent missing question.
15. ~~Add remaining state languages~~ — **DONE.** 12 languages live as of this session.
16. Fix the trilingual gap in benefit text (scheme names/descriptions for the 6 original Maharashtra schemes aren't uniformly translated across all languages yet — this is a much smaller job now than the 2,163-scheme verification was, but still open).

## Track D — Make it work for an actual village user, not just "works in testing"

17. Assume low data/low literacy: keep messages short, numbered replies only (already doing this) — don't add anything that assumes fast scrolling or reading long paragraphs.
18. Decide if WhatsApp-only is enough. WhatsApp needs a smartphone + internet; if your target villages have meaningful feature-phone/no-data populations, you may need an SMS or IVR fallback eventually. Worth deciding now rather than after launch.
19. Test with 5–10 real people from your actual target demographic (not just yourself/family) before wide rollout. Watch where they get confused, not just whether they complete it.
20. Plan distribution: a WhatsApp number is useless if nobody knows it exists. Options: flyers through a local panchayat/gram sabha, partnering with an NGO already working in target villages, a simple poster with the number + a QR code to start a chat.

## Track E — Legal/safety pass before public launch

21. Get at least a basic read on India's DPDP Act (data protection law) given you're collecting income, disability, marital status, caste-linked scheme eligibility over WhatsApp. A cheap one-time lawyer consult is worth it here — I can help you understand the law but can't certify compliance.
22. Make sure the disclaimer (bot gives guidance, not guaranteed scheme approval) is shown early in the flow, not buried at the end.

## Track F — Launch

23. Soft launch to one village/group first. Watch Sentry/logs for errors, watch a simple counter of "started flow" vs "completed flow" to see where people drop off.
24. Iterate on Track C/D based on real usage.
25. Wider rollout once soft launch is stable.

## Track G — Housekeeping this dataset needs before Claude Code touches it

27. Do a dedicated pass on the 331 `needs_review` records — these are the ones with a genuine open question (conflicting sources, a flagship figure in dispute, a scheme whose survival under a new government is unconfirmed). Search `schemes_audit.md` / the JSON for `"status": "needs_review"` to pull the list. Highest-value subset: anything touching a large-population flagship scheme (Goa's Griha Aadhar, Odisha's rggbkmny, Bihar's Kanya Utthan Yojana, Punjab's smsm, several state old-age pensions with conflicting figures).
28. Several `discontinued` records are pure scraping duplicates (e.g. `xyz(1)`, `xyz(2)` suffixes) rather than real scheme discontinuations — worth a quick de-duplication pass on the raw JSON before it's fed into the new rules engine, so the engine doesn't have to special-case them.
29. Re-run this whole verification pass roughly once a year — government schemes revise amounts every April in many states, and this session already caught multiple year-old "current" figures that had since changed.

---
**Right now, the single highest-leverage action is the rules-engine rewrite (#13)** — the data work that used to be the bottleneck is finished, and every day the bot ships without it, all 2,163 verified schemes sit unused except for Maharashtra's original 13. Twilio/Meta verification (#1–3) is the other thing worth kicking off in parallel, since it's the only remaining step with a multi-day clock you don't control and it doesn't block anything else.
