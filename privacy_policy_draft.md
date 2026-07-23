# Apna Haqq — Privacy Policy & Disclaimer (Draft)

*Draft for legal/compliance review before publishing — not yet reviewed by a lawyer.*

## What this is

Apna Haqq is a WhatsApp chatbot that asks you a few questions and tells you which Indian government welfare schemes you may be eligible for.

## What we collect

To match you to schemes, we ask for: your state, age range, gender, yearly income range, ration card type, bank account status, occupation, marital status, caste category, disability status, land ownership, and construction/unorganized-worker board registration status.

We also receive your WhatsApp phone number automatically as part of how WhatsApp messaging works.

We do **not** ask for your name, Aadhaar number, exact address, or any document uploads.

## How we use it

Your answers are used only to check which scheme criteria you meet, inside this one conversation. We do not sell, share, or use this data for advertising.

## How long we keep it

Your answers are deleted as soon as you finish the conversation. If you start but don't finish, your answers are automatically deleted within 24 hours.

## Who can see it

No one at Apna Haqq or Tri City manually reviews your conversation. We do not keep human-readable logs of what you told the bot. (In practice, this means if something goes wrong we can only debug from error messages and aggregate counts — not by reading back what a specific person said — so a support request like "why didn't scheme X show up for me" may require you to walk us through your answers again rather than us looking them up.)

## This is guidance, not a guarantee

Apna Haqq gives informational guidance based on the eligibility rules we could confirm from official sources. It is **not** a government service, does not submit any application on your behalf, and does not guarantee approval. Always confirm final eligibility and required documents at your nearest Aaple Sarkar / Jan Seva Kendra or the scheme's official website before relying on this information. Scheme amounts and rules change, especially around April each year — the information here may be out of date.

## Your rights

Message apnahaqq1947@gmail.com to ask what data we hold about you or to request it be deleted. We will respond and act on it manually.

## Contact

apnahaqq1947@gmail.com

---
**Note for you (not for publication):** all placeholders are now filled per your decisions on 2026-07-23 — 24h/immediate retention (matches what the code actually does after the Redis session fix), no human log review, and apnahaqq1947@gmail.com as the single contact for both general questions and DPDP requests. Two things still genuinely need you or a lawyer, not me: (1) the DPDP Act read (Track E #21) — this draft's "your rights" section is a reasonable-sounding process, not a compliance certification, and (2) confirm "no human log review" is operationally realistic before publishing — it means committing to debug production issues without ever reading a raw conversation. If that turns out to be unworkable once the bot is live, this section needs to change before, not after, you tell users it's true.
