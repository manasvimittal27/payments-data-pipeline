# Data Quality Report: Payments Pipeline, January–March 2026

**Prepared by:** Manasvi Mittal · **Scope:** gateway and legacy in-store payments, refunds,
chargebacks, merchant master (2 systems), partner-bank settlement file

> Portfolio project on synthetic data. The pipeline's output was checked against the
> generator's true record and matches it exactly (`outputs/verification.json`).

## Summary

After cleaning, the payments data is fit for reporting. 152,670 payments from 400 merchants
(₹48.3 crore captured) passed all 37 data tests. The material issues are in the **settlement
file from the bank**, not in our own systems: ₹19.3 lakh unpaid, and fees charged above
contract for four merchants. One feed-design risk, the legacy time zone, would cost ₹1 crore
of mis-dated payments if anyone loads that feed carelessly.

| # | Finding | Records | Value | Severity | Owner |
|---|---|---|---|---|---|
| 1 | Settlements missing from the bank file | 119 merchant-days | ₹19.34 lakh | High | Treasury / bank ops |
| 2 | Bank fees above contracted MDR (+0.25 pp) | 100 merchant-days, 4 merchants | ₹8,722 | High | Finance / bank relationship |
| 3 | Bank paid merchant IDs we don't recognise | 3 lines, 2 IDs | ₹31,538 | High | Treasury, Compliance |
| 4 | Duplicate settlement lines in bank file | 95 | (confirm not paid twice) | High | Bank ops |
| 5 | Legacy feed in local IST, not UTC | 13,268 rows; 3,068 at risk | ₹1.0 crore at risk | High | Data engineering |
| 6 | Payments with missing or unknown merchant IDs | 450 | ₹15.6 lakh | High | Gateway team |
| 7 | Zero or negative payment amounts | 150 | n/a | High | Gateway team |
| 8 | Refunds exceeding payment, orphan or duplicate refunds | 120 | ₹3.2 lakh | High | Refunds team |
| 9 | CRM vs onboarding merchant conflicts | 23 merchants | n/a | Medium | Sales ops |
| 10 | Unrecognised chargeback reason codes | 7 | ₹7,521 | Medium | Disputes team |
| 11 | Replayed gateway batch | 1,115 rows | n/a | Medium | Gateway team |
| 12 | Status-update records, formatting (currency, method case) | ~25,000 | n/a | Low | Handled in pipeline |

## 1. Settlement reconciliation

Expected settlement is calculated from our own data: captured payments, minus refunds,
minus fees (contracted MDR + 18% GST), paid the next day (T+1). It is matched to the bank file
per merchant per day, with a ₹1 tolerance.

| Status | Merchant-days | Difference |
|---|---|---|
| Matched | 31,582 (99.3%) | ₹0 |
| Missing in bank file | 119 | ₹19,33,949 |
| Fee mismatch | 100 | ₹8,722 |
| Unexpected in bank file | 3 | ₹31,538 |

**Fee mismatch, diagnosed from the data.** Dividing the bank's fee by our gross shows the
rate the bank actually applied. It is exactly 0.25 pp above contract for four merchants,
starting 2 March:

| Merchant | Contracted MDR | Bank applied | Days | Underpaid |
|---|---|---|---|---|
| M30118 | 2.00% | 2.25% | 31 | ₹6,677 |
| M30199 | 2.00% | 2.25% | 29 | ₹466 |
| M30240 | 1.75% | 2.00% | 31 | ₹1,522 |
| M30367 | 2.00% | 2.25% | 9 | ₹57 |

A single uniform step on one date points to a pricing table not updated at the bank, not to
random error.

**Recommendations**
- **Missing settlements:** raise a claim with the bank for all 119 merchant-days, oldest first.
- **Fees:** dispute the fee difference and ask the bank to correct the rate table.
- **Unknown IDs:** treat payouts to unrecognised merchant IDs as a compliance question,
  not just a finance one.

## 2. Source data issues

**Time zones (highest-impact design risk).** The gateway sends UTC; the legacy in-store
feed sends local IST as `DD/MM/YYYY HH:MM:SS`. The pipeline parses each correctly. Read as
UTC, every legacy payment after 18:30 IST, 3,068 payments worth ₹1.0 crore, would move to
the next business date. Each moved payment would then show up as a settlement break.
**Recommendation:** document each feed's time zone in the source definitions, and add a test
that compares daily legacy volumes with terminal batch totals.

**Duplicates and status updates.** Each payment is reduced to one record with its most
final status (captured over failed over authorized). This collapsed 1,115 replayed rows and
13,098 superseded "authorized" records.
**Recommendation:** have the gateway send an event ID, so replays can be rejected on load.

**Invalid records (quarantined, 720 total).**
- **Payments (600):** missing merchant ID (200), unknown merchant ID (250), zero or negative
  amount (150).
- **Refunds (120):** for payments that don't exist (60), larger than the payment (58),
  apparent duplicate refunds (2).

None reaches the reporting tables. Each is listed with its reason in `audit.dq_quarantine`
for the owning team to fix at source.

**Merchant master.**
- **Conflicts:** the CRM disagrees with the onboarding system on 21 merchants' category,
  lacks one merchant, and holds one merchant ID the onboarding system doesn't.
- **Pipeline rule:** the onboarding system is the authoritative source for category, pricing
  and status.
- **Recommendation:** sync the CRM from it, not the other way round.

## 3. Controls in place

| Control | Type | Result |
|---|---|---|
| Keys unique and not null in every mart | dbt generic tests | Pass |
| Payments only for known merchants, positive amounts, valid statuses | dbt generic tests | Pass |
| Every payment in the fact table or in quarantine | Singular test (completeness) | Pass |
| Refunds never exceed the payment | Singular test | Pass |
| Captured totals equal across layers | Singular test (reconciliation) | Pass |
| ≥ 99% of settlements reconcile | Singular test, warn level | Pass (99.3%) |
| Unknown merchant IDs in raw payments | Warn-level test | Warn (450 rows, quarantined) |
| Unrecognised chargeback codes | Warn-level test | Warn (7 rows, flagged) |

All tests run in CI on every change (GitHub Actions and GitLab CI), so a broken model or a
new data problem is caught before it reaches a report.

## Limitations

- **Synthetic data.** Real source systems have more varied and subtler problems.
- **Simplified settlement.** Settlement is modelled as daily, calendar T+1, with one fee
  rate per merchant. Real settlement has holidays, reserves and tiered pricing.
- **Placeholder reason codes.** The RuPay chargeback codes in the reference list are
  illustrative.
