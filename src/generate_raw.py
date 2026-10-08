"""
Generate raw extracts from the source systems of a (fictional) payments business, with
realistic data quality problems injected.

Approach: build a CLEAN truth first (what really happened), derive the bank's settlement
file from it, then write the raw extracts the way source systems actually deliver them:
mixed formats, replayed batches, status-update records and some junk. A correct pipeline
recovers the truth exactly; anything it cannot is a data quality finding.

Raw files (data/raw/):
  gateway_payments.csv       payment gateway extract (most rows UTC ISO timestamps)
  legacy_pos_payments.csv    legacy in-store terminal feed (IST 'DD/MM/YYYY HH:MM:SS')
  refunds.csv                refund system extract
  chargebacks.csv            chargeback feed from the card networks
  merchants_onboarding.csv   merchant onboarding system (authoritative master)
  merchants_crm.csv          sales CRM copy of merchant data (not authoritative)
  bank_settlements.csv       settlement file received from the partner bank

All data is synthetic.
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(11)
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
IST = pd.Timedelta(hours=5, minutes=30)
START_IST, END_IST = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-03-31 23:59:59")
DAYS = (END_IST.normalize() - START_IST).days + 1

# ------------------------------------------------------------------ merchants (truth)
N_M = 400
CATS = {"apparel_ecommerce": (1200, .7), "electronics": (8000, .8), "food_restaurants": (450, .5),
        "travel": (9000, .8), "education": (3000, .9), "healthcare": (1500, .8), "digital_goods": (300, .6)}
cat = rng.choice(list(CATS), N_M, p=[.22, .12, .22, .1, .12, .1, .12])
mids = np.array([f"M{30000 + i}" for i in range(N_M)])
mdr = rng.choice([1.75, 1.85, 2.0, 2.2], N_M, p=[.3, .3, .3, .1])
merchants = pd.DataFrame({"merchant_id": mids, "legal_name": [f"Merchant {i:03d} Pvt Ltd" for i in range(N_M)],
                          "category": cat, "mdr_pct": mdr,
                          "onboarded_on": (pd.Timestamp("2023-01-01") + pd.to_timedelta(rng.integers(0, 1000, N_M), "D")).date,
                          "status": rng.choice(["active", "active", "active", "suspended"], N_M, p=[.9, .0, .04, .06])})
merchants.loc[merchants["status"] == "suspended", "status"] = "active"   # keep all active in truth
legacy_pos = rng.random(N_M) < 0.15        # merchants with in-store terminals on the legacy feed

# ------------------------------------------------------------------ payments (truth, IST time)
rate = rng.gamma(2.0, 2.0, N_M)
rows = []
for i in range(N_M):
    n = rng.poisson(rate[i] * DAYS)
    med, sig = CATS[cat[i]]
    t_ist = START_IST + pd.to_timedelta(rng.integers(0, DAYS * 86400, n), "s")
    amt = np.round(np.exp(np.log(med) + sig * rng.standard_normal(n)).clip(10), 2)
    method = rng.choice(["card", "upi", "netbanking"], n, p=[.4, .5, .1])
    feed = np.where(legacy_pos[i] & (rng.random(n) < 0.6), "legacy_pos", "gateway")
    method = np.where(feed == "legacy_pos", "card", method)
    rows.append(pd.DataFrame({"merchant_id": mids[i], "ts_ist": t_ist, "amount": amt, "method": method, "feed": feed}))
pay = pd.concat(rows, ignore_index=True).sort_values("ts_ist").reset_index(drop=True)
pay["payment_id"] = [f"pay_{k:07d}" for k in range(len(pay))]
pay["network"] = np.where(pay["method"] == "card", rng.choice(["visa", "mastercard", "rupay"], len(pay), p=[.45, .35, .2]), "")
pay["status"] = "captured"
failed = rng.random(len(pay)) < 0.06             # genuinely failed payments (not settled)
pay.loc[failed, "status"] = "failed"

# refunds (truth): processed by IST date, deducted on settlement of that date
cap = pay[pay["status"] == "captured"]
ref = cap[rng.random(len(cap)) < 0.04].copy()
ref["refund_ts_ist"] = ref["ts_ist"] + pd.to_timedelta(rng.integers(3600, 10 * 86400, len(ref)), "s")
ref = ref[ref["refund_ts_ist"] <= END_IST]
ref["refund_amount"] = np.where(rng.random(len(ref)) < .8, ref["amount"], np.round(ref["amount"] * rng.uniform(.2, .9, len(ref)), 2))
ref["refund_id"] = [f"rfnd_{k:06d}" for k in range(len(ref))]

# chargebacks (truth) on card payments
card = cap[cap["method"] == "card"]
cb = card[rng.random(len(card)) < 0.004].copy()
cb["received_date"] = (cb["ts_ist"] + pd.to_timedelta(rng.integers(7, 45, len(cb)), "D")).dt.normalize()
cb = cb[cb["received_date"] <= END_IST]
VISA = ["10.4", "13.1", "13.3", "12.6"]; MC = ["4837", "4855", "4853", "4834"]; RUPAY = ["1061", "1065"]
cb["reason_code"] = [rng.choice(VISA if n == "visa" else MC if n == "mastercard" else RUPAY) for n in cb["network"]]
cb["chargeback_id"] = [f"cb_{k:05d}" for k in range(len(cb))]
cb["stage"] = rng.choice(["first_chargeback", "representment", "pre_arbitration"], len(cb), p=[.7, .25, .05])

# ------------------------------------------------------------------ bank settlement file (truth, T+1)
cap = pay[pay["status"] == "captured"].copy()
cap["d"] = cap["ts_ist"].dt.normalize()
g = cap.groupby(["merchant_id", "d"])["amount"].sum().rename("gross")
ref["d"] = ref["refund_ts_ist"].dt.normalize()
r = ref.groupby(["merchant_id", "d"])["refund_amount"].sum().rename("refunds")
st = pd.concat([g, r], axis=1).fillna(0).reset_index()
st["mdr_pct"] = st["merchant_id"].map(dict(zip(mids, mdr)))
st["fees"] = (st["gross"] * st["mdr_pct"] / 100 * 1.18).round(2)                    # MDR + 18% GST
st["net"] = (st["gross"] - st["refunds"] - st["fees"]).round(2)
st["settlement_date"] = st["d"] + pd.Timedelta(days=1)
# Bank-side errors
old_mdr = rng.choice(mids, 4, replace=False)                                          # bank still uses old MDR in March
m_old = st["merchant_id"].isin(old_mdr) & (st["d"] >= "2026-03-01")
st.loc[m_old, "fees"] = (st.loc[m_old, "gross"] * (st.loc[m_old, "mdr_pct"] + 0.25) / 100 * 1.18).round(2)
st.loc[m_old, "net"] = (st.loc[m_old, "gross"] - st.loc[m_old, "refunds"] - st.loc[m_old, "fees"]).round(2)
missing = rng.random(len(st)) < 0.004
bank = st[~missing].copy()
dup = bank.sample(frac=0.003, random_state=3)
unexpected = pd.DataFrame({"merchant_id": ["M39998", "M39999", "M39999"], "settlement_date": pd.to_datetime(["2026-02-10", "2026-03-04", "2026-03-05"]),
                           "gross": [15000.0, 8200.0, 9100.0], "refunds": [0.0, 0.0, 0.0]})
unexpected["fees"] = (unexpected["gross"] * 0.02 * 1.18).round(2); unexpected["net"] = unexpected["gross"] - unexpected["fees"]
bank = pd.concat([bank, dup, unexpected], ignore_index=True)
bank["utr"] = [f"UTR{rng.integers(10**11, 10**12)}" for _ in range(len(bank))]
bank_out = bank[["settlement_date", "merchant_id", "gross", "refunds", "fees", "net", "utr"]].rename(
    columns={"gross": "gross_amount", "refunds": "refund_amount", "fees": "fee_amount", "net": "net_amount"})
bank_out["settlement_date"] = pd.to_datetime(bank_out["settlement_date"]).dt.strftime("%Y-%m-%d")

# ------------------------------------------------------------------ raw extracts (as delivered)
def fmt_utc(ts_ist):
    return (ts_ist - IST).dt.strftime("%Y-%m-%dT%H:%M:%SZ")

gw = pay[pay["feed"] == "gateway"].copy()
lp = pay[pay["feed"] == "legacy_pos"].copy()
ingest = lambda ts: (ts - IST + pd.to_timedelta(rng.integers(60, 7200, len(ts)), "s")).dt.strftime("%Y-%m-%dT%H:%M:%SZ")

gw_raw = pd.DataFrame({
    "payment_id": gw["payment_id"], "merchant_id": gw["merchant_id"], "created_at": fmt_utc(gw["ts_ist"]),
    "amount": gw["amount"].map(lambda v: f"{v:.2f}"), "currency": "INR", "method": gw["method"],
    "card_network": gw["network"], "status": gw["status"], "ingested_at": ingest(gw["ts_ist"])})
# (1) inconsistent casing / formatting
m = rng.random(len(gw_raw)) < 0.03; gw_raw.loc[m, "currency"] = rng.choice(["inr", "", " INR"], m.sum())
m = rng.random(len(gw_raw)) < 0.05; gw_raw.loc[m, "method"] = gw_raw.loc[m, "method"].str.upper()
# (2) status-update (CDC) records: an earlier 'authorized' row for some captured payments
cdc = gw_raw[gw_raw["status"] == "captured"].sample(frac=0.10, random_state=5).copy()
cdc["status"] = "authorized"
cdc["ingested_at"] = (pd.to_datetime(cdc["ingested_at"]) - pd.Timedelta(minutes=30)).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
# (3) replayed batch: exact duplicate rows
replay = gw_raw.sample(frac=0.008, random_state=6)
# (4) junk: null merchant, unknown merchant, zero/negative amount (test transactions)
junk = gw_raw.sample(600, random_state=7).copy()
junk["payment_id"] = [f"pay_x{k:05d}" for k in range(len(junk))]
junk.iloc[:200, junk.columns.get_loc("merchant_id")] = ""
junk.iloc[200:450, junk.columns.get_loc("merchant_id")] = rng.choice(["M39990", "M39991", "M39992", "TESTMERCH"], 250)
junk.iloc[450:, junk.columns.get_loc("amount")] = rng.choice(["0.00", "-1.00", "-499.00"], 150)
gw_raw = pd.concat([gw_raw, cdc, replay, junk], ignore_index=True).sample(frac=1, random_state=8)

lp_raw = pd.DataFrame({
    "txn_ref": lp["payment_id"], "mid": lp["merchant_id"], "txn_time_local": lp["ts_ist"].dt.strftime("%d/%m/%Y %H:%M:%S"),
    "amount_paise": (lp["amount"] * 100).round().astype(int), "network": lp["network"].str.upper(),
    "txn_status": np.where(lp["status"] == "captured", "SUCCESS", "DECLINED")})

ref_raw = pd.DataFrame({"refund_id": ref["refund_id"], "payment_id": ref["payment_id"],
                        "created_at": fmt_utc(ref["refund_ts_ist"]), "amount": ref["refund_amount"].map(lambda v: f"{v:.2f}"),
                        "status": "processed"})
bad_ref = ref_raw.sample(120, random_state=9).copy()
bad_ref["refund_id"] = [f"rfnd_x{k:04d}" for k in range(len(bad_ref))]
bad_ref.iloc[:60, bad_ref.columns.get_loc("amount")] = (bad_ref["amount"].astype(float).iloc[:60] * 1.5 + 100).map(lambda v: f"{v:.2f}")
bad_ref.iloc[60:, bad_ref.columns.get_loc("payment_id")] = [f"pay_9{k:06d}" for k in range(60)]
ref_raw = pd.concat([ref_raw, bad_ref], ignore_index=True)

cb_raw = pd.DataFrame({"chargeback_id": cb["chargeback_id"], "payment_id": cb["payment_id"], "network": cb["network"],
                       "reason_code": cb["reason_code"], "amount": cb["amount"].map(lambda v: f"{v:.2f}"),
                       "received_date": cb["received_date"].dt.strftime("%Y-%m-%d"), "stage": cb["stage"]})
m = rng.random(len(cb_raw)) < 0.06
cb_raw.loc[m, "reason_code"] = rng.choice(["10.40", "4837 ", "", "UNKNOWN"], m.sum())

mo = merchants.copy()
crm = merchants[["merchant_id", "legal_name", "category"]].copy()
conf = rng.random(N_M) < 0.06
crm.loc[conf, "category"] = rng.choice(list(CATS), conf.sum())
crm = crm[crm["merchant_id"] != mids[5]]                       # CRM missing a merchant
crm = pd.concat([crm, pd.DataFrame({"merchant_id": ["M39990"], "legal_name": ["Old Lead Pvt Ltd"], "category": ["travel"]})])

for name, df in [("gateway_payments", gw_raw), ("legacy_pos_payments", lp_raw), ("refunds", ref_raw),
                 ("chargebacks", cb_raw), ("merchants_onboarding", mo), ("merchants_crm", crm), ("bank_settlements", bank_out)]:
    df.to_csv(RAW / f"{name}.csv", index=False)

# truth summary used to verify the pipeline
truth = {"captured_payments": int((pay["status"] == "captured").sum()),
         "captured_amount": round(float(pay.loc[pay["status"] == "captured", "amount"].sum()), 2),
         "refunds": len(ref), "chargebacks": len(cb), "settlement_rows_expected": len(st),
         "bank_missing": int(missing.sum()), "bank_duplicates": len(dup), "bank_unexpected": len(unexpected),
         "old_mdr_merchants": sorted(old_mdr.tolist()), "old_mdr_rows": int((m_old & ~missing).sum())}
pd.Series(truth).to_json(RAW.parent / "truth.json", indent=2)
print({k: len(v) for k, v in [("gateway", gw_raw), ("legacy_pos", lp_raw), ("refunds", ref_raw), ("chargebacks", cb_raw), ("bank", bank_out)]})
print(truth)
