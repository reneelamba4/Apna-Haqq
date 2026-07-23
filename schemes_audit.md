# Apna Haqq — Scheme Data Audit

Last checked: July 14, 2026. Re-run this check at least once a year — several of these schemes revise amounts every April, and eKYC/beneficiary lists get purged mid-year.

## Verified and fixed in app.py

**Ladki Bahin Yojana** — Rs.1,500/month, women aged 21-65, family income ≤Rs.2.5L. Confirmed unchanged (a promised increase to Rs.2,100 has not been implemented as of July 2026). Added: mandatory annual eKYC (Jun-Jul window) — Maharashtra removed ~70 lakh beneficiaries in a 2026 verification drive for false income claims, tax-payee status, and Aadhaar mismatches. Being "eligible on paper" no longer means payment is guaranteed.

**PM Kisan Samman Nidhi** — Rs.6,000/year in 3 installments of Rs.2,000. Confirmed current (23rd installment paid June 2026).

**PMJJBY / PMSBY** — Rs.436/year for Rs.2L life cover, Rs.20/year for Rs.2L accident cover. Confirmed current (rates unchanged since the June 2022 revision).

**MGNREGA — bug found and fixed.** Code had Rs.273/day. Actual Maharashtra rate for FY2025-26 (effective April 2025) is Rs.312/day. Updated in code with a note that this is revised centrally every April.

**Ayushman Bharat / MJPJAY — bug found and fixed.** Maharashtra expanded MJPJAY/PMJAY to cover *every* resident of the state as of July 2024, not just BPL/ration-card holders. The old code only offered this scheme to people with low income or a ration card, which would have wrongly told plenty of eligible people they didn't qualify. Fixed to show this scheme to everyone, with the extra Rs.1.5L renal cover flagged separately for Orange/Yellow ration card holders.

**NFSA free grain — corrected.** Code said "5kg/person" flat for anyone with a ration card. Actually: AAY (Yellow card) households get 35kg per *household*; Priority/BPL (Orange card) households get 5kg per *person*. Both are free (no cost at the shop) and guaranteed until Dec 2028. Fixed to split by card type.

**PM Ujjwala — corrected, was overstated.** Code called this a "free cooking gas connection." It isn't fully free: Rs.1,600 (14.2kg cylinder) or Rs.1,150 (5kg) connection assistance, plus a Rs.300/refill subsidy capped at 4 refills/year (down from 9). Also now requires Aadhaar eKYC or the subsidy doesn't get paid. Reworded to be accurate.

**Old Age Pension (NSAP + Shravan Bal) — corrected.** Code said vaguely "Rs.200-500/month + Maharashtra top-up." The actual combined total in Maharashtra is Rs.1,500/month either way (Rs.200 central + Rs.1,300 state for ages 60-79; Rs.500 central + Rs.1,000 state for 80+). Fixed to state the real total.

**PM Jan Dhan Yojana** — Rs.2L accidental insurance confirmed, but it only stays active if the RuPay card is used at least once every 90 days — added that caveat. Overdraft up to Rs.10,000 confirmed.

## All-India database (July 15, 2026)

Pulled 2,153 unique schemes from myScheme.gov.in (India's official central scheme aggregator, MeitY/Digital India Corporation) via a public structured mirror. This replaces the "13 schemes" base — full file is `schemes_database_raw.json`. Every record has a `verification` field so status is never silently assumed; 1,402 of 2,153 carry a specific ₹ amount and are flagged higher-priority to verify, since amounts are what goes stale.

**Verified so far: 19 of 2,153.** Real, sourced, dated verification — not the full database. Everything else is honestly marked "sourced, not yet independently verified."

**Sanjay Gandhi Niradhar Yojana (destitute/"widow" pension) — bug found and fixed.** Raw data had the old pre-Dec-2024 rate (Rs.600/month). Current confirmed rate is Rs.1,500/month via DBT. Also broader than "widow pension" — covers destitute or disabled people, seriously ill, abandoned/divorced women, transgender people, and unmarried women 35+, not just widows. Fixed in app.py.

**Inter-caste marriage incentive — bug found and fixed.** Raw data had old tiered amounts topping out around Rs.50,000. Current combined incentive is Rs.3,00,000 total (Rs.50,000 state + Rs.2,50,000 from the Dr. Babasaheb Ambedkar Foundation) when one partner is SC/ST/VJ/NT/SBC. Roughly 6x higher than what the old data showed.

**Confirmed accurate, no changes needed:** Namo Shetkari Mahasanman Nidhi (Rs.6,000/year, stacks with PM-KISAN), Gopinath Munde Shetkari Apghat Suraksha (Rs.2L accident compensation), CMEGP (15-35% business subsidy), LIDCOM Margin Money Loan, LIDCOM 50% Subsidy Scheme, LIDCOM Gattai Stall Scheme, disability self-employment schemes (FADSE, FASETDP), VJNT post-matric scholarship maintenance rates.

**Flagged, do not trust yet:** Financial Assistance for Aids and Appliances for Disabled Persons (FAAADP) — raw data and current search results give conflicting figures (Rs.1,500-3,000 tiers vs. a Rs.15,000 cap mentioned elsewhere), possibly two different scheme versions. Don't surface a specific amount for this one until read against a primary source directly, not search snippets.

## Maharashtra — complete (48/48 schemes touched, July 15 2026)

Ran 4 parallel research passes to finish the state. Real errors found, several larger than anything caught so far:

**Shahu, Phule, Ambedkar Award** — was listed at Rs.15,00,000. Actual amount is Rs.7,50,000 — exactly double. Also wrong award count (raw said 7 regional awards, actually 12: two per each of 6 revenue divisions).

**Karma Veer Dadasaheb Gaikwad Sabalikaran & Swabhiman Yojana** — a landless-farmer land grant scheme. Raw data said 50% subsidy + 50% loan; a December 2025 government order changed this to a fully free 100%-subsidized land grant. The bot would have told people to expect a loan obligation that no longer exists.

**LIDCOM Education Loan Scheme** — both the loan cap and interest rate were wrong. Raw: Rs.10L (India) / Rs.20L (abroad) at 4%/3.5%. Actual: Rs.30L / Rs.40L at 6-7% interest. Also missing an income cap (Rs.3L/year household) that raw data didn't have at all.

**Karmaveer Padmashri Dadasaheb Gaikwad Prize** — raw data described one Rs.51,000 payout to "winner + institute." It's actually two separate award tracks: Rs.21,000 to an individual, Rs.30,000 to an organization.

**State Pre-Matric Scholarship For Disabled** — a Maharashtra Cabinet decision on April 1, 2026 raised these rates significantly (e.g. Class 9-10 went from Rs.200/month to Rs.600-800/month) and the raw data still shows the old tiers. Only news coverage found so far, not the formal Government Resolution — flagged to confirm once the GR is indexed.

**Grant In Aid To Old Age Home** and two agriculture schemes (Bhausaheb Fundkar horticulture subsidy, CM Agriculture and Food Processing Scheme) had no specific ₹ figure in the raw data at all — now filled in with sourced amounts.

**Flagged, not confirmed — do not surface exact figures yet:** Nanaji Deshmukh Krishi Sanjivani Prakalp (POCRA) has conflicting subsidy percentages across sources (45-80% depending on source, possibly conflating two different schemes). Tuition/Exam Fees to VJNT Students has an income-tier structure that doesn't match what's findable online. Financial Assistance for Aids and Appliances for Disabled Persons still unresolved from the earlier batch.

**11 small VJNT/SBC scholarship variants** (things like the ITI stipend, Sainik School allowance, junior college funding) were left as "pattern-consistent, not individually re-checked" — their rates match the confirmed baseline (the ones we did check, like the Savitribai Phule girls' scholarships and Post-Matric Scholarship, came back exactly matching raw data), and MahaDBT's portal confirms the whole scheme family is live for AY2025-26, but each individual figure wasn't freshly searched. Lower risk given the small size of these schemes and internal consistency, but worth a pass before high-volume use.

**Not yet checked:** One Stop Centre (181) — generic helpline description, low risk since it's not a cash benefit.

Maharashtra total: 34 schemes verified with sources, 11 pattern-consistent but not individually re-checked, 3 flagged as unreliable pending better sources. That's the full 48. Remaining work: all 526 central schemes and ~1,580 other-state schemes, to be worked through state by state.

## Gujarat — 116 of 118 schemes touched (July 15 2026)

Ran 5 parallel research passes (agriculture equipment, animal husbandry, SC education/welfare, labour welfare boards, women/social schemes). 83 verified with sources, 27 pattern-consistent but not individually re-checked, 6 flagged unreliable, 2 not yet reviewed (Agricultural Skill Development Training for Women Farmers, Vanbandhu Kalyan Yojana).

**Biggest finding: Gujarat's two state health insurance schemes have merged, same pattern as Maharashtra.** Mukhyamantri Arogya Artham Yojana and Mukhyamantri Amrutum Yojana combined into a unified "PMJAY-MA" card on 17 Oct 2024, integrated with central Ayushman Bharat. Rs.5,00,000/family/year cashless. The bot should show ONE entry here, not two separate legacy schemes with different old amounts.

**Dr. Savitaben Ambedkar Inter-Caste Marriage Assistance** — raw data said Rs.1,00,000. The official Gujarat government page says Rs.50,000 (Rs.25,000 cash + Rs.25,000 in savings certificates). Half the amount — same category of error as the Maharashtra inter-caste marriage scheme, different direction.

**Janta Juth Accident Insurance (farmer accident cover)** — raised from Rs.2,00,000 to Rs.4,00,000 for death/permanent disability in the FY2025-26 state budget. Raw data still shows the old range.

**Sahuji Maharaj Award (top SC students, Std X/XII)** — rates raised by a government resolution dated 7 April 2025. State-level 1st prize is now Rs.51,000, not Rs.41,000; 2nd is Rs.41,000, not Rs.21,000.

**Vahli Dikri Yojana (girl child scheme)** — income limit is actually Rs.2,00,000, not Rs.6,00,000 as raw data claimed — 3x too high, meaning the bot would have told plenty of ineligible families they qualified. Also recovered the full payout structure: Rs.4,000 (Class 1) + Rs.6,000 (Class 9) + Rs.1,00,000 at age 18.

**Divyang Lagna Sahay (disability marriage assistance)** — mixed-couple rate raised from Rs.50,000 to Rs.75,000 in June 2025.

**Dr. Ambedkar Awas Yojana (SC housing)** — flagged, not corrected. Official page shows Rs.50,000 (urban) / Rs.70,000 (rural), over 50% lower than raw data's Rs.1,20,000. Could be a superseded top-up or a different scheme entirely — needs a dedicated re-check before publishing either figure.

**National Agriculture Insurance Scheme** — likely defunct in Gujarat. Replaced nationally by PMFBY in 2016, and Gujarat exited PMFBY itself in 2020 in favor of its own Mukhyamantri Kisan Sahay Yojana. Recommend removing this entry rather than surfacing it to users.

Full list of every scheme's status is in `schemes_database_raw.json` under each record's `verification` field.

## West Bengal — all 29 schemes touched (July 15 2026)

**New category of risk, not just stale numbers: a change of state government invalidated entire flagship schemes overnight.** West Bengal had a state election in May 2026 — BJP won, ending 15 years of TMC rule. The new government didn't just adjust rates, it discontinued signature programs from the previous administration:

**Lakshmir Bhandar — West Bengal's biggest flagship scheme, discontinued.** This was the closest thing WB had to Maharashtra's Ladki Bahin Yojana (a large cash-transfer scheme for women). As of June 1, 2026 it's been replaced entirely by "Annapurna Bhandar" — a flat Rs.3,000/month for all eligible women, no SC/ST split, excluding tax filers and government employees. The raw data's Rs.1,000/Rs.500 figures describe a scheme that no longer exists in that form.

**State Welfare Scheme For Purohits — discontinued.** The new government scrapped this and the parallel Imam/Muezzin stipend scheme in May 2026 as part of ending religion-based honorariums.

**Six pension schemes (old age, disability, widow, ST/SC-specific) are in an unresolved transition.** Rs.1,000/month is what's currently being paid, but a rate increase (competing Rs.1,500 vs Rs.2,000 proposals from the outgoing and incoming governments) has been publicly announced but not formally notified as of this check. Flagged as "verified but in flux" rather than picking a number — publishing an unconfirmed figure here would be guessing.

**Takeaway for the ongoing process:** a change in state government should now be treated as its own trigger for re-verification, separate from the annual cadence — not just a rate check, whole schemes can vanish or get replaced. Worth watching for this pattern in any state we haven't gotten to yet if there's been a recent election.

Beyond the political story, real data-quality bugs also turned up: **Amar Fasal Amar Gola** was mischaracterized entirely — raw data described it as a seed/fertilizer subsidy; it's actually a storage/godown infrastructure scheme. **Krishak Bandhu** (the state's big farmer income scheme) was missing its Rs.2 lakh death benefit component. **Kanyashree Prakalpa** (WB's UN-recognized girls' education scheme) had the wrong income ceiling category — Rs.1.2 lakh/year, not the Rs.2.5 lakh used for most other WB schemes, meaning the bot would have wrongly told higher-income families they qualified.

29 of 29 schemes assessed: most verified/corrected with sources, 2 discontinued, 2 flagged as genuinely unclear even after searching (BM-SSY pension amount, Samajik Mukti's income limit looks implausibly high and can't be resolved without the actual gazette notification).

## Tamil Nadu — all 113 schemes touched (July 16 2026)

**Biggest finding: a scheme was actively wrong, not just stale.** The **Amma Two Wheeler Scheme for Working Women (atwsfww)** has been **discontinued since 2021** — no new applications accepted, and it remains closed through 2026 under the current government. The raw data presented it as a live subsidy. This is now marked `discontinued` and should never be surfaced to a user.

**Second-biggest: a pension rate conflict needing manual resolution.** Tamil Nadu's cabinet raised state-funded pensions in 2023, but two research passes came back with different numbers depending on scheme type: old-age and widow pensions (ignoapstn, ignwpstn, dwps, ddwps) appear to have moved from Rs.1,000 to **Rs.1,200/month** (Aug 2023), while the disability pension (daps, igndpstn) appears to have moved specifically to **Rs.1,500/month** (Jan 2023) — a different, higher rate than the general pension bump. Both figures come from real sources but conflict with several secondary sites claiming Rs.1,500-2,000 across the board. Marked `needs_review`; recommend confirming against the actual Government Order before publishing exact figures.

**CMCHIS (Chief Minister's Comprehensive Health Insurance) — did NOT merge with Ayushman Bharat/PMJAY**, unlike Maharashtra's MJPJAY and Gujarat's equivalents. Tamil Nadu instead runs a hybrid model since 2018 where CMCHIS is the master scheme and PMJAY beneficiaries are subsumed within it — one card serves both. Coverage is Rs.5,00,000/family/year across ~1,700 hospitals. Worth noting as a genuinely different integration pattern from the other two states checked so far.

**Zero Ticket Bus Travel for Women — recently renamed.** As of July 2026 (this month), the scheme was rebranded from "Magalir Vidiyal Payanam" to "Magalir Payanam" under the current administration — same benefit (free travel up to 30km), just dropped the old branding term. The bot will use a generic label so it doesn't confuse anyone who's seen either name.

**A likely-discontinued COVID-era scheme flagged, not confirmed.** The Migrants Employment Generation Programme (megp, for COVID-return migrants) shows no evidence of 2025/2026 activity and its official page has a stale 2023 footer — marked `needs_review` rather than `discontinued` since no formal closure notice was found either way.

**Several income-ceiling and amount discrepancies caught:** the marriage assistance for daughters of poor widows scheme cites a Rs.72,000/year ceiling in the raw data vs. Rs.1,20,000/year in current sources; the free sewing machine scheme has the same conflict; the Labour Welfare Board marriage assistance was understated at Rs.10,000 (actual Rs.20,000, with a higher salary ceiling too); and the "afm" marriage assistance for disabled persons was listed at just Rs.2,000 when the real figure follows the standard Rs.25,000-50,000 + gold coin template used elsewhere in the state.

**One scheme possibly folded into another:** the Moovalur Ramamirtham Ammaiyar marriage-assistance scheme (mranmas1) may no longer be disbursed as a standalone grant — several sources say it was absorbed into the Pudhumai Penn higher-education scheme around 2022-23. Flagged rather than removed, pending direct confirmation.

Of the 21 disability schemes, 12 fully confirmed, 8 flagged `needs_review` (mostly rate/tier disputes across conflicting official-looking sources — Tamil Nadu's primary scd.tn.gov.in site is JS-rendered and unreachable by automated search, so verification leaned on district (.nic.in) mirror pages that don't always agree with each other), 1 has no verifiable source at all. The ~40 niche business-subsidy and arts-recognition-award schemes were only spot-checked (3 business subsidies, the Kalaimamani award family) given they're not means-tested welfare benefits typical users would search for — marked `plausible_unconfirmed` rather than individually verified.

113 of 113 schemes assessed: 1 discontinued, roughly two dozen flagged `needs_review` for rate/eligibility conflicts across sources, the rest confirmed or reasonably assumed plausible.

## Central (national) schemes — all 539 touched (July 16 2026)

**Reprioritization: central schemes matter more than any single state's, because every user of the bot is potentially eligible regardless of where they live.** The database had 539 schemes tagged as central/national (level=`central_or_general`, mostly untagged to any state) — bigger than any individual state's scheme count. These were verified before continuing to the next state.

**Real correction that was already live in app.py, now fixed:** PM Ujjwala's refill subsidy cap was recorded as "cut from 9 to 4 refills/year." Current research shows this was wrong — Cabinet approved Rs.300/refill for up to **9 refills/year** for FY2025-26 (Rs.12,000 crore outlay, confirmed via PMIndia/PIB). Fixed in `app.py`. Also confirmed via this same pass: Pradhan Mantri Matru Vandana Yojana now pays an *additional* Rs.6,000 for a second child if it's a girl (on top of the existing Rs.5,000 for the first child) — this wasn't in our data and isn't yet wired into `match()`, worth adding once the rules-engine rewrite happens.

**Several schemes turned out to be materially different from what the snapshot implied:**

- **Beti Bachao Beti Padhao (BBBP)** has no individual cash benefit at all — it's a national awareness/advocacy campaign, not a direct-benefit scheme. The bot must never tell a user they get money from BBBP.
- **Mahila Samman Savings Certificate** is closed to new deposits since April 2025 (was a 2-year window, not renewed).
- **SWADHAR Greh** was merged and renamed "Shakti Sadan" back in 2021-22 — the old name no longer refers to an active standalone scheme.
- **Scheme for Adolescent Girls (SAG)** was discontinued in its original nationwide form (2022) and replaced by a version restricted to Aspirational Districts + North-Eastern states only — not available everywhere.
- **Maulana Azad National Fellowship** is closed to new applicants since 2022-23 (existing beneficiaries continue, with reported payment delays).
- **Paramparagat Krishi Vikas Yojana** (organic farming support) — the snapshot's Rs.50,000/hectare figure is wrong; current rate is Rs.31,500/hectare.
- **Pradhan Mantri Mudra Yojana** — loan ceiling was raised from Rs.10 lakh to Rs.20 lakh (new "Tarun Plus" tier) via Budget 2024-25; the snapshot's Rs.10 lakh cap is outdated.
- **PMGKP** (COVID-era health worker insurance) is fully discontinued — don't surface it.
- Several post-matric/pre-matric OBC/EBC scholarship schemes have been folded into the umbrella **PM-YASASVI** scheme since 2021-22 under new income-ceiling rules (mostly Rs.1 lakh/year, not the Rs.2.5 lakh figure that actually applies to the separate SC/ST scholarship track) — the old scheme names/slugs persist in the dataset but the actual administering scheme has changed.

**Scale management:** given 539 schemes, effort was weighted toward the ~90 broad, high-reach welfare/pension/health/education/agriculture/employment schemes an ordinary citizen would realistically match to (all individually verified with sources above). The remaining ~450 are niche institutional programs — PhD/postgraduate research fellowships, sports and culture recognition awards, coffee-growing-region subsidies, defense/ex-servicemen niche benefits, MSME industry-specific subsidies — that a welfare-eligibility bot's typical user is very unlikely to match to. These were spot-checked in clusters rather than individually verified (marked `plausible_unconfirmed`), following the same reasoning already applied to Tamil Nadu's business/arts schemes. No evidence of widespread discontinuation was found across this category during spot-checks — recognition awards and institutional subsidy programs tend to persist for years once established, unlike some of the big cash-transfer schemes that get rebranded or discontinued after elections.

539 of 539 central schemes assessed: ~90 broad schemes individually verified/corrected with sources, several genuinely wrong or discontinued items caught and flagged, ~450 niche institutional programs spot-checked and batch-noted as low priority.

## Andhra Pradesh + Telangana — all 36 schemes touched (July 16 2026)

**Same pattern as West Bengal, twice over.** Both states had a change of government since the myScheme snapshot was taken: Andhra Pradesh (YSRCP to TDP, mid-2024) and Telangana (BRS to Congress, Dec 2023). Nearly every flagship scheme in both states was literally branded with the previous Chief Minister's name or initials (YSR, Jagananna, KCR) — and almost all of them have since been renamed, restructured, or in one case suspended entirely.

**Andhra Pradesh renames (old name → new name, most also came with a rate increase):**
- YSR Aarogyasri (health insurance) → **Dr. NTR Vaidya Seva** (Rs.5,00,000 cover retained, but flag a hospital-dues/suspension risk reported in 2025)
- Jagananna Amma Vodi (mother/child school support) → **Thalliki Vandanam**, raised to Rs.15,000/year (net Rs.13,000)
- Jagananna Videshi Vidya Deevena (overseas education loans) → **Ambedkar Overseas Vidya Nidhi**
- Pedalandariki Illu (housing) → likely superseded by **Andariki Illu**, exact continuation status of the old scheme unclear
- YSR Pension Kanuka (old age/widow/disability pension) → **NTR Bharosa**, raised to Rs.3,000/month
- YSR Rythu Bharosa (farmer income support) → **Annadata Sukhibhava**, raised to Rs.20,000/year
- YSR Vahana Mitra (driver support) → **AP Vahana Mitra**, raised to Rs.15,000/year
- YSR Cheyutha (women's financial assistance) was the one notable exception — name unchanged, still active as-is.

**Telangana renames/discontinuations:**
- **Dalit Bandhu** (Rs.10 lakh/family SC self-employment grant) — the single biggest finding. This is effectively suspended: accounts frozen, no new applications, a year of unresolved pending applications. A replacement ("Dr. B.R. Ambedkar Abhaya Hastham," Rs.12 lakh) was promised but not implemented as of this check. The bot must NOT tell users they're eligible for this.
- 2BHK Housing Scheme → **Indiramma Illu**
- Haritha Haram (tree plantation) → **Vanamahotsavam**
- KCR Nutrition Kit → **MCH Kit** (contents unchanged, name/photo of former CM removed)
- Kalyana Lakshmi / Shaadi Mubarak (marriage assistance) — name and Rs.1,00,116 amount unchanged, but widely reported payment delays (only ~43% of FY2025-26 allocation actually disbursed) — flag as a disbursement-delay risk, not an eligibility change.
- Rythu Bima (farmer life insurance) — confirmed continued and expanded under the new government, one of the few schemes that survived the transition untouched. Don't confuse with the separate "Rythu Bharosa" input-support scheme.

**Takeaway reinforced again:** any scheme carrying a former Chief Minister's name or initials should be treated as a near-certain rename/discontinuation candidate after any election, not just a routine rate check. This is now the third state (after West Bengal) where this exact pattern showed up.

36 of 36 schemes assessed: multiple confirmed renames with new names and updated rates, one effectively suspended scheme flagged, a handful still needing direct portal confirmation.

## Karnataka — all 24 schemes touched + 5 new flagship schemes added (July 16 2026)

**Different outcome than West Bengal/Andhra Pradesh/Telangana.** Karnataka also had a change of government (BJP to Congress, May 2023), but unlike those three states, none of Karnataka's existing 24 schemes showed a renaming/discontinuation pattern — these are corporation-administered welfare schemes (SC/ST/minority welfare boards), not personality-branded ones, so they survived the government change untouched.

**The real finding here was a gap, not a rename.** Karnataka's Congress government launched 5 large "guarantee" schemes in 2023 — Gruha Jyothi (free electricity), Gruha Lakshmi (cash to women heads of household), Anna Bhagya (free rice), Yuva Nidhi (unemployment allowance), and Shakti (free bus travel for women) — and **none of these were in the database at all.** These are almost certainly the schemes an ordinary Karnataka user would most commonly match to, so their absence was a bigger accuracy risk than any individual rate being stale. Added as 5 new records:

- **Gruha Jyothi**: up to 200 units/month free electricity (domestic connections, both APL/BPL)
- **Gruha Lakshmi**: Rs.2,000/month direct to bank account of the female head of household
- **Anna Bhagya**: 10kg free rice/person/month for BPL/AAY/priority-household cardholders
- **Yuva Nidhi**: Rs.3,000/month (graduates) or Rs.1,500/month (diploma), up to 2 years, age 18-25, unemployed 6+ months post-graduation
- **Shakti**: free bus travel for all women on Karnataka government buses, no registration required

**Other corrections found in the existing 24:** the Bhagyalakshmi girl-child scheme changed structure in 2021 (from an LIC lump-sum model to Rs.3,000/year into a Sukanya Samriddhi Account); Nekar Samman Yojana (weaver support) increased from Rs.2,000 to Rs.5,000; the Udyogini women's entrepreneurship loan cap was recorded as a flat Rs.1,00,000 but is actually Rs.3 lakh with 30-50% subsidy; Ganga Kalyana's borewell assistance varies by district (Rs.3-5 lakh) rather than being one flat figure; and Thayi Bhagya (maternal healthcare) is geographically limited to 7 specific backward districts, not statewide — important for the bot's matching logic once wired in.

24 of 24 existing schemes assessed + 5 new flagship schemes added: most confirmed or corrected with sources, 2 flagged `needs_review` (Devadasi Children's Marriage amount, Madilu Kit cash-equivalent value) pending direct portal confirmation.

## Kerala — all 75 schemes touched (July 16 2026)

**Different failure mode than any state so far: not wrong amounts, wrong structure.** No political renaming here (Kerala's LDF government has been continuously in power) — the problem was that a large share of the 75 raw figures were single flat numbers standing in for what are actually tiered, percentage-based, or in-kind benefits. At least 12 of the 75 schemes needed this kind of structural correction, not just a rate update:

- **Scholarships/educational assistance for disabled students, transgender students, children of disabled parents, OEC pre-matric assistance, Prathibha Scholarship** — all tiered by class/year/hostel status, not one flat number. A student in class 1 and a PG student get very different amounts under the same scheme name.
- **Two schemes are in-kind, not cash**: Mandahasam (free dentures for seniors) and Snehayanam (free electric auto-rickshaw for mothers of children with disabilities) — neither pays out a rupee figure the way the snapshot implied.
- **Two schemes had "coverage ceiling" figures the snapshot presented as flat payouts**: Thalolam and Cancer Suraksha are both Rs.50,000 *initial* ceilings that a hospital committee can extend further — effectively closer to cashless treatment than a one-time Rs.50,000 check.
- **Nearly every Kerala MSME scheme checked (asha, ess, ofoe, rrsdmsmecpu, sisnhe, slswe, smmgnu, ksmsmerrs) turned out to be a percentage-of-project-cost subsidy or interest-subvention rate with a rupee cap, not a flat grant amount** — the snapshot's single-figure amounts for these were essentially all wrong in the same way.

**A genuinely confusing cluster got disambiguated:** four similarly-named schemes — Snehasparsham, Snehasanthwanam, Snehapoorvam, and Sastraposhini — cover completely different things (unwed mothers; Endosulfan pesticide-exposure victims; orphaned/single-parent children's education; and a school science-lab infrastructure grant, respectively). Sastraposhini in particular is not an individual citizen benefit at all — the money goes to schools, not families — and should probably be excluded from citizen-facing eligibility results entirely rather than presented as something a person can apply for.

**Two items flagged for direct follow-up rather than guessed at:** the Ex-Convicts financial assistance scheme has conflicting Rs.10,000/Rs.15,000 figures across sources, and the KSCSTE research-fellowship family (15 niche PhD/postdoc programs, low priority for this bot) shows signs of a stipend revision (one figure came back at Rs.60,000/month vs. the Rs.45,000 in our data) that would need a dedicated re-check if those ever become relevant.

75 of 75 schemes assessed: most corrected from flat-figure to tiered/percentage/in-kind structure, 2 items flagged `needs_review` pending direct department confirmation, 15 niche research fellowships spot-checked and batch-noted.

## Rajasthan + Madhya Pradesh — all 152 schemes touched (July 16 2026)

**Rajasthan had a change of government too (Congress to BJP, Dec 2023) — same rename pattern as West Bengal/Andhra Pradesh/Telangana, confirmed on the two biggest schemes in the state:**

- **Mukhyamantri Chiranjeevi Swasthya Beema Yojana** (Gehlot's flagship Rs.25 lakh health insurance scheme) → renamed **Mukhyamantri Ayushman Arogya Yojana**, coverage amount unchanged.
- **Rajiv Gandhi Krishak Sathi Sahayata Yojana** (farmer accident assistance) → renamed **Mukhyamantri Krishak Sathi Yojana**, and the amount actually quadrupled from Rs.50,000 to Rs.2,00,000.
- **Rajiv Gandhi Scholarship for Academic Excellence** (study-abroad scholarship) → renamed **Swami Vivekananda Scholarship for Academic Excellence**.
- One scheme, **Indira Gandhi Shehri Credit Card Yojana**, looks like it may be fully defunct — new loan sanctions reportedly stopped in March 2022, before the election even happened, with no sign of continuation or replacement. Flagged rather than presented as live.
- Not everything Congress-branded got touched, though — **Mukhyamantri Work From Home-Job Work Yojana** (Gehlot-era, 2022) survived the government change completely intact under the same name.

**Rajasthan's bigger accuracy problem wasn't politics, it was collapsed tiers.** A large share of the farm-infrastructure and construction-worker schemes had single flat figures standing in for category-dependent or tier-dependent amounts — farm pond subsidies vary by caste category and by whether the pond is lined or unlined (Rs.63,000 to Rs.1,35,000 for what the snapshot called one number), and two separate construction-worker death-benefit schemes (normal death ~Rs.75,000 vs. accidental death Rs.5,00,000) were at risk of being confused with each other, which matters a great deal to a grieving family checking the bot.

**Madhya Pradesh had no change of government** (continuously BJP, though the CM changed within-party from Shivraj Singh Chouhan to Mohan Yadav in Dec 2023) — no renaming pattern found here. The headline finding instead: **Ladli Behna Yojana** (MP's flagship, the scheme that inspired Maharashtra's Ladki Bahin) is confirmed at Rs.1,500/month, up from Rs.1,250 — and a widely-discussed political promise of Rs.3,000/month has **not** actually been implemented as of this check, so the bot must not report that higher figure. Ladli Laxmi Yojana (girl-child savings scheme) confirmed unchanged at Rs.1,43,000 total staggered benefit.

**A serious near-miss caught in MP:** the Post Matric Scholarship - MP entry had Rs.2,50,000 recorded as if it were the benefit amount — it is actually the *family income eligibility ceiling* for SC students, not a payout. Publishing that as a benefit would have badly misled a student. Several other MP scholarships had the same flat-figure-hiding-a-tiered-benefit problem seen in Kerala (Shiksha Protsahan Puraskar Yojana ranges from Rs.10,000 to Rs.25,000 depending on course; Khiladi Protsahan Yojana is up to Rs.50,000, not a flat Rs.10,000).

**Roughly a third of both states' schemes came back `needs_review`** rather than confirmed — mostly smaller Rajasthan construction-worker sub-benefits and MP pension/scholarship variants where no reliable current source turned up in this pass. These are flagged rather than guessed at, and are the natural next candidates for a dedicated follow-up search against the relevant department portals directly (sje.rajasthan.gov.in, socialjustice.mp.gov.in) rather than general web search.

152 of 152 schemes assessed: 3 confirmed political renames (2 in Rajasthan) with updated names/rates, roughly half corrected from flat-figure to tiered/percentage structure, about a third flagged `needs_review` pending direct department confirmation.

## Uttar Pradesh + Chhattisgarh — 113/113 schemes touched (July 17 2026)

**Uttar Pradesh's headline finding: a pension hike, not a rename.** The Yogi Adityanath government raised the Old Age, Widow, and Divyang pensions from Rs.1,000/month to Rs.1,500/month in a mid-2026 revision — this affects the largest beneficiary population of any single fix in this batch, and the old Rs.1,000 figure across all three schemes was stale. Separately, Kanya Sumangala Yojana — UP's flagship girl-child scheme — was under-reporting the total benefit: it rose from Rs.15,000 to Rs.25,000 (effective 2024), paid across 6 milestones from birth through Class 12 graduation. Kanya Sumangala is high-visibility and high-volume, so this was a priority fix.

**The marriage-assistance cluster turned out to be a genuine mess, not just a bot bug.** Four separate database entries (Kanya Vivah Sahayata Yojana, Marriage Grant Scheme, Marriage Incentive Reward Scheme, Mukhyamantri Samuhik Vivah Yojana) looked like duplicates but are at least two distinct real programs run by different departments with different eligible populations — KVSY is restricted to registered construction workers' daughters (Rs.55,000-65,000), while MSVY is a general-public mass-marriage scheme with a benefit figure that's genuinely inconsistent across sources (Rs.51,000 vs Rs.1,00,000 breakdown). Rather than guess, these were flagged `needs_review` — telling a general-public user they qualify for a construction-worker-only benefit would be a real error, not a rounding issue.

**Chhattisgarh confirmed the "change of government" risk again, precisely as predicted.** Chhattisgarh flipped Congress (Bhupesh Baghel) to BJP (Vishnu Deo Sai) in Dec 2023, and — following the same pattern already seen in West Bengal, Andhra Pradesh, Telangana, and Rajasthan — the Rajiv Gandhi-branded flagship scheme was discontinued. **Rajiv Gandhi Kisan Nyay Yojana**, Baghel's per-acre farmer income support scheme, has been replaced by **Krishak Unnati Yojana**, a paddy procurement bonus taking the effective price to Rs.3,100/quintal (MSP Rs.2,300 + Rs.800 state bonus), paid via DBT instead of the old input-subsidy structure. Its companion scheme, Rajiv Gandhi Gramin Bhoomihin Krishi Majdoor Nyay Yojana (landless labourer income support), carries the same politically risky branding but couldn't be confirmed either way — flagged `needs_review` rather than assumed discontinued, since no direct post-2023 source was found. Notably, **Godhan Nyay Yojana** (Baghel's cow-dung-purchase scheme) survived the change of government intact and was even expanded — it wasn't Gandhi-branded, which lines up with the pattern that survival correlates with branding, not with which party is popular.

**Chhattisgarh's other big issue was the same flat-figure-hides-a-tiered-benefit problem seen repeatedly in Kerala and Rajasthan/MP.** Several "maternity assistance" schemes for unorganized/sanitation workers were recorded as flat Rs.4,200 payments when the real structure is staged (Rs.4,200 + Rs.2,800 + Rs.3,000, up to Rs.10,000 total). Construction-worker housing assistance was corrected from Rs.50,000 to the real Rs.1,00,000. Death/disability assistance across multiple worker-board schemes turned out to be two-tier (normal vs. worksite-accidental) rather than one flat figure, mirroring the exact confusion risk already fixed in Rajasthan's construction-worker death benefits.

113 of 113 schemes assessed: 1 confirmed political replacement (Rajiv Gandhi Kisan Nyay Yojana to Krishak Unnati Yojana) with updated figures, roughly a third corrected from flat-figure to staged/tiered structure, and a meaningful share flagged `needs_review` — particularly the UP marriage-assistance cluster and Chhattisgarh's second Rajiv Gandhi-branded scheme, both of which need direct department-portal confirmation before the bot states a specific benefit.

## Haryana + Uttarakhand + Delhi + Bihar + Jharkhand — 138/138 schemes touched, 1 new scheme added (July 17 2026)

**Delhi was the headline finding, exactly as flagged going in.** Delhi flipped AAP to BJP in Feb 2025 (Rekha Gupta, CM) after a decade of AAP government, and the pattern held again: **Delhi Ladli Scheme**, AAP's flagship girl-child scheme, closed March 31, 2026 and was replaced by **Lakhpati Bitiya Yojana** (phased payments totaling Rs.56,000 birth-to-graduation, plus a Rs.1,00,000 maturity payout) starting April 2026. The old Ladli terms (Rs.36,000 maturity) are no longer being offered — the bot must not tell a user they'll get the old scheme. A second AAP-era scheme, Jai Bhim Mukhyamantri Pratibha Vikas Yojana, is officially "on hold" pending government amendments — flagged `needs_review` rather than presented as live. Notably, Mukhyamantri Tirth Yatra Yojana (free pilgrimage travel for seniors) and even the Congress-branded Rajiv Gandhi Swavlamban Rojgar Yojna both survived the change of government untouched — reinforcing that survival tracks with a scheme's specific political branding, not with a general change in power.

**A genuinely new scheme was discovered and added to the database, not just corrected.** The new Delhi government launched Mahila Samridhi Yojana in March 2025 — a Rs.2,500/month direct cash transfer to eligible women, BJP's answer to AAP's promised-but-never-implemented Mahila Samman Yojana. This didn't exist in the original snapshot at all. Given it's a high-visibility cash scheme, it was added as a new record (`dmsy`) rather than left missing, following the same pattern used for Karnataka's 5 guarantee schemes earlier in this project.

**Bihar and Jharkhand had no change of government** (NDA and JMM both continued, though Bihar's CM changed from Nitish Kumar to Samrat Chaudhary, BJP, in April 2026 within the same coalition) — no renaming pattern found. The real finding was a large, confirmed pension hike: Bihar's Mukhyamantri Vridhjan Pension Yojna jumped from Rs.400/500 per month to a flat **Rs.1,100/month**, effective July 2025, announced ahead of the state election — this is a big enough jump that it was worth flagging as the headline Bihar fix. Bihar's Kanya Utthan Yojana (its own flagship girl-child scheme) hit the same problem seen in Rajasthan/MP/UP: sources disagree sharply on the total benefit (roughly Rs.54,100 in current sources vs. an older Rs.94,100 figure), so it's marked `needs_review` pending direct confirmation rather than guessed at.

**Haryana surfaced its own quiet-lapse case, similar in shape to Chhattisgarh's second Rajiv Gandhi scheme.** Rajiv Gandhi Family Insurance Scheme is still listed on official Haryana government pages with no rename, but a separate source states it actually ceased in 2017 with beneficiaries shifted to the central PMSBY scheme — the government pages appear to be stale rather than actively maintained. Rather than trust the still-live-looking page, this was flagged `needs_review` as likely discontinued, since telling a family to apply for a dead scheme is exactly the kind of error this whole project exists to prevent. Haryana's real, active pensions (Old Age Samman Allowance, Widow Pension) both got a confirmed hike to Rs.3,200/month effective Nov 2025.

**Uttarakhand's main fix was disambiguation, not a rename.** Two similarly-named girl-child schemes, Nanda Gaura Yojana and Mukhyamantri Mahalaxmi Yojana, looked like they might be duplicates or a merged scheme — they aren't. Nanda Gaura pays cash (Rs.11,000 at birth + Rs.51,000 on passing Class 12), while Mahalaxmi provides an in-kind birth kit only, with no fixed cash value. Conflating them would have either overstated or understated what a family actually receives.

138 of 138 schemes assessed: 1 confirmed political replacement (Delhi Ladli to Lakhpati Bitiya) plus 1 new scheme added (Delhi Mahila Samridhi Yojana), 1 likely-quiet-lapse flagged (Haryana's Rajiv Gandhi Family Insurance Scheme), 1 major pension hike confirmed (Bihar, Rs.400/500 to Rs.1,100/month), and a meaningful share of smaller construction-worker-board schemes across all five states flagged `needs_review`/`plausible_unconfirmed` pending direct portal confirmation.

## Odisha + Himachal Pradesh + Assam — 163/163 schemes touched, 2 new schemes added (July 17 2026)

**Odisha was the single richest rename batch of this whole project so far.** Odisha ended 24 years of BJD (Naveen Patnaik) rule in 2024, replaced by BJP (Mohan Charan Majhi) — the longest single-party run of any state checked in this audit — and the rename pattern was correspondingly large. **KALIA**, BJD's single biggest flagship farmer income-support scheme, was scrapped and replaced by **CM-KISAN Yojana** (small/marginal farmers Rs.4,000/yr, landless agricultural households Rs.12,500/yr). **Biju Swasthya Kalyan Yojana**, Odisha's health insurance flagship, was renamed **Gopabandhu Jana Arogya Yojana** and merged with PM-JAY. **Biju Pucca Ghar Yojana** (housing) became **Antyodaya Gruha Yojana**. Even the Biju Patnaik Sports Awards — six separate award categories — were renamed **Odisha Rajya Krida Samman**. Not every "Biju"-branded scheme fell, though: Biju Swasthya, Biju Pucca Ghar, and the sports awards were renamed, but schemes honoring the more historically-distant Gopabandhu Das (a freedom fighter, not a BJD figure) and Madhu Babu Pension Yojana (retained its name, just given a large benefit increase to Rs.3,000-3,500/month) survived intact — reinforcing that it's proximity to the outgoing party's living political figures that drives renaming, not just any legacy branding.

**A new flagship scheme was added: Subhadra Yojana**, BJP's answer to Ladki Bahin/Ladli Behna, launched Sept 2024 — Rs.10,000/year to women aged 21-60, Rs.50,000 total over the scheme's 5-year run. Over 1 crore women were already enrolled by late 2024, making this a near-certain lookup for the bot.

**Himachal Pradesh (BJP to Congress, Dec 2022) showed a milder version of the same pattern.** Most BJP-era "Mukhya Mantri"-branded schemes (HIMCARE health insurance, Sahara Yojana for chronic illness, Kanyadaan Yojana) were confirmed continuing under Congress with no rename — generic "Chief Minister" branding appears to survive transitions better than personally-branded schemes elsewhere. The state's real gap was a second new flagship: **Indira Gandhi Pyari Behna Samman Nidhi Yojana**, Congress's own women's cash-transfer scheme (Rs.1,500/month), which was missing from the database entirely and has been added. One old-age pension figure (`ops`) came back with genuinely conflicting sources — Rs.1,500 flat vs. a Rs.1,000/1,500/1,700 age-and-gender-tiered structure — and was flagged `needs_review` rather than guessed at, since this is a high-reach scheme where an average of two contradictory numbers would just be a new kind of wrong.

**Assam (no change of government, continuously BJP) still had two real corrections.** Orunodoi, Assam's flagship women's cash-transfer scheme, was raised from Rs.830 to Rs.1,250/month. Atal Amrit Abhiyan, an older health insurance scheme, was formally discontinued in the 2023-24 budget and folded into Ayushman Asom-MMJAY — the database had it listed as if still standalone and live.

163 of 163 schemes assessed: 4 confirmed political renames in Odisha (KALIA, Biju Swasthya Kalyan, Biju Pucca Ghar, Biju Patnaik Sports Awards) plus 2 new flagship schemes added (Subhadra Yojana - Odisha, Indira Gandhi Pyari Behna Samman Nidhi Yojana - Himachal Pradesh), 1 scheme found formally discontinued in Assam, and a meaningful share of smaller welfare-board and technical schemes flagged `needs_review`/`plausible_unconfirmed` pending direct department-portal confirmation.

## Goa + Puducherry — 317/317 schemes touched, 1 new scheme added (July 17 2026)

**This was the most granular, lowest-headline-risk batch of the project so far.** Neither Goa (continuously BJP) nor Puducherry (AINRC-BJP alliance since 2021, no flip) had a change of government, and the two territories' scheme lists are dominated by dozens of small, narrowly-scoped subsidy and welfare-board line items — fisheries equipment subsidies, construction-worker welfare-board benefits, MSME industry incentives, and Sainik (ex-servicemen) welfare grants — rather than the kind of large flagship cash-transfer schemes that dominated earlier states. The real risk here wasn't political renaming, it was sheer volume: with over 300 narrow technical schemes, a much larger share than usual had to be honestly marked `needs_review` or `plausible_unconfirmed` rather than guessed at, since official Goa and Puducherry department portals (gbocwwb.goa.gov.in, labour.py.gov.in, socwelfare.py.gov.in) were frequently unreachable by simple fetch this round, likely JavaScript-rendered pages that need a browser-level check rather than a search-snippet check.

**Goa's one real headline finding was a flagship discrepancy, not a rename.** Griha Aadhar Scheme, Goa's women's cash-transfer scheme, has an official DWCD document stating Rs.1,500/month, while several third-party aggregator sites claim Rs.2,500/month — since this is the highest-reach scheme in the whole Goa batch, it was flagged `needs_review` rather than either figure being picked at random; the wrong choice here would affect the most people. Separately, the Mamta maternity incentive (paid for delivering a girl child) was confirmed to have been hiked to Rs.10,000, and CM Sawant's May 2026 Labour Day announcement added a new Rs.25,000 construction-injury benefit plus five more worker schemes not yet individually catalogued — a new placeholder record was added to flag this for a dedicated follow-up pass rather than losing track of it.

**Puducherry's headline finding was that Congress-branded legacy names survived completely intact.** Rajiv Gandhi Social Security Scheme For Poor Families (2012) is still active under its original name with recent 2025 disbursement orders, even though Puducherry's government hasn't been Congress-led in years — reinforcing the pattern (also seen in Delhi's Rajiv Gandhi Swavlamban Rojgar Yojna and Haryana's Rajiv Gandhi schemes) that welfare-board and social-security scheme names tend to be administratively "sticky" regardless of which party is renaming flagship programs elsewhere. Old Age and Destitute Pension was corrected from a flat figure to its real age-tiered structure (Rs.1,500/2,000/3,000/month), with a possible Rs.3,500 top-tier hike from a Sept 2025 announcement flagged as unconfirmed rather than assumed universal.

317 of 317 schemes assessed: 0 confirmed political renames (first batch in this project with none), 1 new scheme placeholder added pending a Goa worker-welfare follow-up pass, 1 flagship figure discrepancy flagged in Goa (Griha Aadhar), and a substantially larger-than-usual share of narrow technical/subsidy schemes marked `needs_review`/`plausible_unconfirmed` given how many official Puducherry and Goa department portals could not be directly fetched this round.

## Final batch — Meghalaya, Arunachal Pradesh, Tripura, J&K, Chandigarh, Andaman & Nicobar, Manipur, Punjab, Nagaland, Mizoram, Sikkim, Central-misc, Lakshadweep, Ladakh, Dadra & Nagar Haveli — 297/297 schemes touched, 2 new schemes added, Punjabi added (July 17 2026)

**This batch closes out the full database — every one of the original ~2,150 schemes plus everything added along the way has now been individually assessed.** It also covered the widest range of political situations of any single batch: two Union Territories with no elected government at all (Chandigarh, Andaman & Nicobar), a state that just exited President's Rule after 11 months (Manipur, elected government sworn in Feb 2026), a state whose whole legislative status changed in 2019 and only regained an elected government in Oct 2024 (Jammu & Kashmir), and an AAP government that unseated Congress in Punjab in 2022.

**Punjab delivered the batch's biggest headline: a mid-flight scheme overhaul.** Punjab's health insurance scheme was upgraded from the income-capped Sarbat/Mukh Mantri Sehat Bima Yojana to Mukh Mantri Sehat Yojana effective January 2026 — coverage doubled to Rs.10 lakh/family/year and the income eligibility cap was removed entirely, making it universal for all Punjab residents. The old database entry, which gated eligibility by income, would have wrongly told plenty of people they didn't qualify for what is now a universal benefit. Separately, AAP's long-delayed manifesto promise of Rs.1,000/month for women (Mukh Mantri Mawan Dheeyan Satkar Yojana) finally started paying out on July 1, 2026 — literally the same month as this check — and has been added as a new scheme, flagged for a quick re-check given how fresh the rollout is.

**Manipur required a different kind of care: a whole state's schemes under a leadership-continuity cloud.** With an elected government only 5.5 months old after 11 months of President's Rule, every "Chief Minister"-branded scheme from the prior administration (N. Biren Singh, who resigned amid the 2023 ethnic conflict) was flagged `needs_review` rather than assumed to be continuing — including one pandemic-era livelihood scheme (CM's COVID-19 Affected Livelihood Support Scheme) confirmed expired, and a college-student rehabilitation scheme tied directly to the conflict whose continuation under the new government is genuinely unconfirmed.

**Tripura's ASSP was found formally migrated to a central scheme** — Asangathita Shramik Sahayika Prakalpa was folded into the central Pradhan Mantri Shram Yogi Maan-dhan back in 2019, so the bot must redirect unorganized-worker users to PM-SYM rather than list a dead state scheme. Three Tripura pensions (disability, tribal-head honorarium, journalist pension) were quietly doubled-to-quintupled in amount over the past year, an easy detail to miss without a direct check. Sikkim's transgender award (`sgatt`) was corrected from a flat Rs.2,000/month — which several aggregators still show — to its real, much richer tiered structure (Rs.12,000/month for ages 0-6, free education through graduation, Rs.500/month if still unemployed afterward).

**Two zombie-scheme patterns recurred, one each in Meghalaya and Chandigarh.** Meghalaya's construction-worker board death and marriage benefits have official portal figures (Rs.15,000-50,000 range) sharply lower than what third-party aggregator sites claim (Rs.2-5 lakh) — flagged `needs_review` rather than picking either number. Chandigarh's Old Age, Widow, and Disability pensions have sat at Rs.1,000/month since a 2021 UT Social Welfare Committee recommended doubling them to Rs.2,000 — the Union Government never signed off, so the old, lower rate is still current and shouldn't be second-guessed based on the unimplemented proposal.

297 of 297 schemes assessed: 1 scheme confirmed migrated to a central program (Tripura's ASSP to PM-SYM), 1 major scheme overhaul with eligibility rules removed entirely (Punjab's health insurance), 2 new flagship schemes added (Punjab's women's cash transfer, still mid-rollout), several multi-year-stale pension/allowance figures corrected upward, and — consistent with every UT/small-state batch — a higher-than-average share of niche welfare-board schemes flagged `needs_review`/`plausible_unconfirmed` where official portals were unreachable by simple fetch.

## Running total across all states verified so far — DATABASE FULLY ASSESSED

Maharashtra (48) + Gujarat (116) + West Bengal (29) + Tamil Nadu (113) + Central/National (539) + Andhra Pradesh + Telangana (36) + Karnataka (24 + 5 new) + Kerala (75) + Rajasthan + Madhya Pradesh (152) + Uttar Pradesh + Chhattisgarh (113) + Haryana + Uttarakhand + Delhi + Bihar + Jharkhand (138 + 1 new) + Odisha + Himachal Pradesh + Assam (163 + 2 new) + Goa + Puducherry (317 + 1 new) + Meghalaya/Arunachal Pradesh/Tripura/J&K/Chandigarh/A&N/Manipur/Punjab/Nagaland/Mizoram/Sikkim/Central-misc/Lakshadweep/Ladakh/DNH (297 + 2 new) + 2 stray Gujarat records closed out in a final sweep = **2,163 of 2,163 schemes now individually assessed. Zero remain unverified.**

Breakdown by confidence: 833 `verified` (specific figure or fact confirmed against a named source), 331 `needs_review` (real ambiguity — conflicting sources, stale rates, or eligibility that needs a human decision before publishing), 953 `plausible_unconfirmed` (scheme exists, current figure not independently locatable this pass — mostly small welfare-board/scholarship line items), 46 `discontinued` (confirmed dead, renamed, migrated, or a duplicate scraping artifact).

**What this means in practice:** every scheme in the database now has a documented status instead of a silent assumption. The `verified` and `discontinued` records (879 total) are safe to serve to users as-is. The `needs_review` records (331) are the highest-value follow-up target — these are cases where something is actively wrong or contested, not just unresearched. The `plausible_unconfirmed` records (953, mostly single-digit-rupee-amount welfare-board line items in smaller states) are the long tail — individually low-stakes, but worth a dedicated department-portal scraping pass before the bot states a specific number for any of them.

## Bigger issue found, not a data problem

Scheme *names* and *benefit descriptions* are inconsistently translated. Several schemes (PM Jan Dhan, PMJJBY, PMSBY, MGNREGA) show their name in English only regardless of which language the user picks, and **every benefit description line is English-only, in all cases** — even for Marathi/Hindi users. For a bot whose whole premise is reaching Marathi/Hindi speakers, this defeats part of the purpose. This needs a proper translation pass, not a quick machine-translated patch, since bad translations of eligibility terms could be worse than none. Tracked as a separate task.

## Sources

- [Ladki Bahin Yojana 2026 status](https://www.myscheme.gov.in/schemes/mmlby)
- [Ladki Bahin eKYC and beneficiary removal](https://sarkariyojana.com/ladki-bahin-yojana-ekyc/)
- [PM-Kisan installment status](https://pmkisan.gov.in/)
- [MGNREGA Maharashtra wage rate notification](https://divcompune.maharashtra.gov.in/en/rates-of-unskilled-wages-to-be-paid-to-labourers-under-the-mahatma-gandhi-national-rural-employment-guarantee-scheme-mgnrega/)
- [MGNREGA FY25-26 wage revision](https://www.zeebiz.com/india/news-mahatma-gandhi-national-rural-employment-guarantee-scheme-updates-wages-for-financial-year-2026-haryana-records-highest-of-rs-400-per-day-unskilled-manual-workers-wages-352941)
- [NSAP / Shravan Bal Maharashtra amounts](https://sjsa.maharashtra.gov.in/en/scheme/indira-gandhi-national-old-age-pension-scheme/)
- [PM Jan Dhan Yojana 2026 benefits](https://wiseindia.in/pm-jan-dhan-yojana-2026-guide/)
- [Ayushman Bharat / MJPJAY integration, universal coverage from July 2024](https://www.zppalghar.gov.in/en/scheme/integrated-ayushman-bharat-pradhan-mantri-jan-arogya-yojana-mahatma-jyotirao-phule-jan-arogya-yojana/)
- [NFSA free grain quantities and PMGKAY extension to 2028](https://schemesinindia.in/central/pm-garib-kalyan-anna-yojana-pmgkay)
- [PM Ujjwala Yojana subsidy and eKYC requirement 2026](https://www.egovtschemes.com/pradhan-mantri-ujjwala-yojana-3-0/)
- [Tamil Nadu Differently Abled Welfare Schemes (Ranipet district)](https://ranipet.nic.in/differently-abled-welfare-schemes/)
- [Tamil Nadu Differently Abled Welfare Schemes (Kancheepuram district)](https://kancheepuram.nic.in/departments/district-differently-abled-welfare/differently-abled-welfare-schemes/)
- [Commissionerate for Relief and Rehabilitation, TN (pensions and relief schemes)](https://www.cra.tn.gov.in/)
- [TN cabinet pension hike, August 2023](https://www.outlookindia.com/national/tn-cabinet-gives-nod-to-hike-pension-under-social-security-schemes-news-304985)
- [TN Social Welfare Dept — marriage assistance schemes](https://tnsocialwelfare.tn.gov.in/en/specilisationswoman-welfare/marriage-assistance-schemes)
- [Chief Minister's Girl Child Protection Scheme](https://tnsocialwelfare.tn.gov.in/en/specilisationschild-welfare/chief-ministers-girl-child-protection-scheme)
- [Zero Ticket Bus Travel Scheme rename, July 2026](https://newstodaynet.com/2026/07/10/vidiyal-dropped-from-free-bus-scheme)
- [CMCHIS — Tamil Nadu's hybrid PMJAY model](https://www.orfonline.org/expert-speak/pmjay-tamil-nadus-hybrid-model)
- [Tamil Nadu health insurance schemes guide 2025](https://www.thenewsminute.com/partner/a-complete-guide-to-tamil-nadus-health-insurance-schemes-in-2025)
- [Amma Two Wheeler Scheme discontinuation](https://sarkariyojana.com/amma-two-wheeler-scheme/)
- [TN MSME Dept — Capital Subsidy, NEEDS, BEIS schemes](https://www.msmetamilnadu.tn.gov.in/)
- [Kalaimamani Award status 2026](https://www.egovtschemes.com/kalaimamani-award/)
- [PMUY refill subsidy cabinet approval, 9/year](https://www.pmindia.gov.in/en/news_updates/cabinet-approves-continuation-of-targeted-subsidy-for-pradhan-mantri-ujjwala-yojana-consumers-for-2025-26-at-rs-12000-crore/)
- [PMMVY second-girl-child benefit](https://www.myscheme.gov.in/schemes/pmmvy)
- [Beti Bachao Beti Padhao — no direct cash benefit](https://www.drishtiias.com/daily-news-analysis/beti-bachao-beti-padhao-scheme-1)
- [Mahila Samman Savings Certificate closure](https://www.staffnews.in/2025/04/mahila-samman-savings-certificate-scheme-mssc-sb-order-03-2025.html)
- [SWADHAR Greh renamed Shakti Sadan](https://cleartax.in/s/swadhar-greh-scheme)
- [Scheme for Adolescent Girls restructuring](https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=2040950)
- [Maulana Azad Fellowship discontinuation](https://www.deccanherald.com/india/govt-discontinued-maulana-azad-fellowship-as-it-overlaps-other-schemes-1187342.html)
- [PKVY current per-hectare rate](https://krishijagran.com/explainers/paramparagat-krishi-vikas-yojana-pkvy-how-farmers-can-get-up-to-rs-31-500ha-subsidy-for-organic-farming/)
- [PM Mudra Yojana loan ceiling raised to Rs.20L](https://www.sanskritiias.com/current-affairs/increase-in-limit-of-mudra-loan-scheme)
- [PM-YASASVI umbrella scheme for OBC/EBC/DNT scholarships](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2067373&reg=3&lang=2)
- [ADIP disability aids scheme, revised 2024](https://depwd.gov.in/en/adip/)
- [PMAY-U 2.0 guidelines](https://pmay-urban.gov.in/pmay-u-2.0-guidelines)
- [e-NAM mandi integration figures](https://www.pib.gov.in/PressNoteDetails.aspx?id=158169&NoteId=158169&ModuleId=3&reg=48&lang=2)
- [AP welfare schemes renamed, YSR/Jagananna insignias dropped](https://www.yovizag.com/tdp-renames-ap-welfare-schemes-drops-ysr-jagan-insignias/)
- [Naidu rolls out Thalliki Vandanam (renamed Amma Vodi)](https://theprint.in/politics/naidu-rolls-out-thalliki-vandanam-expanding-jagans-amma-vodi-scheme-24-lakh-more-students-covered/2656370/)
- [Dr. NTR Vaidya Seva dues/suspension report](https://thesouthfirst.com/health/₹2500-crore-in-dues-to-380-hospitals-ntr-vaidya-seva-scheme-suspended-in-andhra/)
- [Telangana Congress govt scraps Dalit Bandhu](https://www.opindia.com/2024/08/telangana-congress-govt-scraps-dalit-bandhu-scheme/)
- [2BHK renamed Indiramma Illu](https://telanganatoday.com/congress-govt-to-distribute-brs-era-double-bedroom-houses-under-indiramma-indlu-scheme)
- [Haritha Haram renamed Vanamahotsavam](https://telanganatoday.com/congress-officially-renames-haritha-haram-as-vanamahotsavam)
- [KCR Nutrition Kit renamed MCH Kit](https://missiontelangana.com/congress-govt-renames-kcr-kits-but-fails-in-ensuring-adequate-supply/)
- [Kalyana Lakshmi/Shaadi Mubarak payment delays](https://telanganatoday.com/telangana-delay-in-kalyana-lakshmi-shaadi-mubarak-benefits-leaves-poor-families-struggling)
- [Karnataka 5 guarantee schemes, budget coverage](https://www.deccanherald.com/india/karnataka/karnataka-budget-2026-live-updates-siddaramaiahs-record-17th-budget-guarantee-schemes-anna-bhagya-gruha-lakshmi-gruha-jyoti-yuva-nidhi-shakti-state-budget-updates-3920713)
- [Karnataka guarantee schemes spend, Rs.95,000cr](https://www.deccanherald.com/india/karnataka/karnataka-govt-spends-rs-95000-cr-on-five-guarantee-schemes-so-far-3704652)
- [Bhagyalakshmi scheme structure change](https://www.govtschemes.in/karnataka-bhagyalakshmi-scheme)
- [Udyogini scheme Karnataka terms](https://www.myscheme.gov.in/schemes/us)
- [Kerala Social Justice Dept scheme index](https://sjd.kerala.gov.in/)
- [Kerala Backward Communities Development Dept schemes](https://bcdd.kerala.gov.in/en/schemes/)
- [Kerala Industries Dept MSME schemes](https://industry.kerala.gov.in/)
- [Snehasanthwanam (Endosulfan victims)](https://socialsecuritymission.gov.in/2024/07/15/snehasanthwanam/)
- [Sastraposhini school lab grant](https://kscste.kerala.gov.in/sastraposhini/)
- [Chiranjeevi Yojana renamed Ayushman Arogya Yojana](https://www.patrika.com/jaipur-news/chiranjeevi-swasthya-bima-yojana-new-update-bhajanlal-government-circular-changed-everything-8734636)
- [Rajiv Gandhi Krishak Sathi renamed, amount quadrupled](https://www.patrika.com/ajmer-news/good-news-for-farmers-bhajanlal-government-changed-rajiv-gandhi-krishak-sathi-sahayata-yojana-and-amount-in-2-lakh-rupees-19145266)
- [Rajiv Gandhi Scholarship renamed Swami Vivekananda Scholarship](https://hte.rajasthan.gov.in/files/uploads/RGSFAQ.pdf)
- [Ladli Behna Yojana current rate](https://cmladlibehnayojana.com/ladli-behna-yojana-eligibility-criteria/)
- [Ladli Laxmi Yojana structure](https://ladlilaxmi.mp.gov.in/)
- [UP pension hike to Rs.1,500/month, 2026](https://newstrack.com/uttar-pradesh/up-pension-hike-2026-yogi-government-increases-monthly-pension-to-rs-1500-608428)
- [Kanya Sumangala Yojana official portal](https://mksy.up.gov.in)
- [UP Kanya Vivah Sahayata Yojana (construction workers)](https://www.myscheme.gov.in/schemes/kvsy)
- [UP Mesy maternity/child benefit structure](https://www.myscheme.gov.in/schemes/mesy)
- [Chhattisgarh Krishak Unnati Yojana replaces Rajiv Gandhi Kisan Nyay Yojana](https://www.drishtiias.com/hindi/state-pcs-current-affairs/chhattisgarh-government-transfers-funds-under-krishak-unnati-scheme)
- [Godhan Nyay Yojana continuation and expansion](https://exhibition.skoch.in/beacon-of-hope/department-of-agriculture-development-and-farmer-welfare-and-biotechnology-government-of-chhattisgarh)
- [Chhattisgarh Labour Dept official scheme registry (BOCW + unorganized worker boards)](https://shramevjayate.cg.gov.in/EngPages/schemes.aspx)
- [Chhattisgarh e-rickshaw subsidy increase reports](https://raigarhtopnews.com/major-decision-at-the-labour-ministers-meeting/)
- [Delhi Ladli Scheme replaced by Lakhpati Bitiya Yojana](https://www.business-standard.com/india-news/delhi-govt-replace-ladli-scheme-lakhpati-bitiya-yojana-key-changes-126021001807_1.html)
- [Delhi Mahila Samridhi Yojana launch](https://www.indiatvnews.com/delhi/delhi-mahila-samriddhi-yojana-free-lpg-subsidy-scheme-bjp-holi-diwali-free-gas-cylinder-2025-03-07-979587)
- [Bihar old age pension hike to Rs.1,100/month](https://www.tribuneindia.com/news/india/from-rs-400-to-rs-1100-cm-nitish-kumar-increases-old-age-pension-in-bihar/)
- [Haryana pension hike to Rs.3,200/month](https://socialjusticehry.gov.in/old-age-samman-allowance-scheme/)
- [Nanda Gaura Yojana official portal, Uttarakhand](https://www.nandagaurauk.in/)
- [KALIA scrapped, replaced by CM-KISAN Yojana](https://odishabytes.com/odisha-chief-minister-mohan-majhi-launches-cm-kisan-yojana-says-46-lakh-farmers-to-benefit/)
- [Biju-branded Odisha schemes renamed by Majhi govt](https://theprint.in/politics/traces-of-biju-patnaik-bjd-scrubbed-off-key-odisha-schemes-rebranded-by-majhis-govt-in-1st-budget/2194559/)
- [Biju Swasthya Kalyan Yojana renamed Gopabandhu Jana Arogya Yojana](https://bsky.odisha.gov.in/)
- [Subhadra Yojana launch, Odisha](https://en.wikipedia.org/wiki/Subhadra_Yojana)
- [Indira Gandhi Pyari Behna Samman Nidhi Yojana, Himachal Pradesh](https://himbumail.com/latest/cm-sukhu-launch-indira-gandhi)
- [Orunodoi Assam raised to Rs.1,250/month](https://orunodoi.assam.gov.in)
- [Atal Amrit Abhiyan discontinued, folded into Ayushman Asom-MMJAY](https://atalamritabhiyan.assam.gov.in/)
- [Goa CM Sawant Labour Day 2026 worker welfare expansion](https://goemkarponn.com/goa-expands-worker-welfare-net-with-death-compensation-new-labour-schemes/)
- [Goa Mamta scheme hiked to Rs.10,000](https://actforgoa.org/incentive-under-mamta-scheme-for-giving-birth-to-girl-child-hiked-to-rs-10k/)
- [Goa Griha Aadhar Scheme official DWCD PDF](https://dwcd.goa.gov.in/uploads/Ghrihaaadhar.pdf)
- [Goa Startup IT Policy incentives](https://startup.goa.gov.in/StartupIncentives)
- [Puducherry Rajiv Gandhi Social Security Scheme, still active 2025](https://puducherry-dt.gov.in/scheme/rajiv-gandhi-social-security-scheme/)
- [Puducherry Old Age and Destitute Pension](https://www.egovtschemes.com/old-age-and-destitute-pension/)
- [Punjab Mukh Mantri Sehat Yojana replaces Sarbat Sehat Bima Yojana, Jan 2026](https://www.smcinsurance.com/government-schemes/articles/mukh-mantri-sehat-yojana-punjab)
- [Punjab Mukh Mantri Mawan Dheeyan Satkar Yojana launch](https://cleartax.in/s/mukh-mantri-mawan-dheeyan-satkar-yojana)
- [Tripura ASSP migrated to central PM-SYM, 2019](https://www.teamleaseregtech.com/updates/article/6815/government-of-tripura-migrates-beneficiaries-under-asanghatita-sramik/)
- [Tripura disability/tribal-head/journalist pension hikes](https://www.business-standard.com/india-news/tripura-increases-monthly-disability-allowance-from-2-000-to-5-000-125082300085_1.html)
- [Sikkim pension scheme official portal](https://pensionscheme.sikkim.gov.in/)
- [Manipur President's Rule ends, elected government Feb 2026](https://bureaucratsindia.in/news/state-government/manipur-gets-elected-government-as-presidents-rule-ends)
- [Chandigarh pension rates, unimplemented 2021 hike proposal](https://chdsw.gov.in/index.php/scheme/old-age-pension)
- [Arunachal Pradesh CMFCCS and Dulari Kanya corrections](https://arunachaltimes.in/index.php/2026/04/27/two-health-schemes-truly-benefitting-the-needy/)
- [J&K State Marriage Assistance Scheme restructured](https://poonch.nic.in/document/implementation-of-state-marriage-assistance-scheme-restructured-for-poor-girls-in-the-district/)
- [Central bonded labourer rehabilitation compensation tiers](https://pib.gov.in/newsite/PrintRelease.aspx?relid=154895)
- [MP Sambal 2.0 / Mukhyamantri Jankalyan Yojana](https://sambal.mponline.gov.in/)
