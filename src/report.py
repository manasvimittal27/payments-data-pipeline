"""Read the dbt-built warehouse and write the data quality report outputs:
CSV extracts, charts, a lineage diagram from dbt's manifest, and a check against the truth file."""
import json
import subprocess
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT, CH = ROOT / "outputs", ROOT / "outputs" / "charts"
CH.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(ROOT / "warehouse.duckdb"), read_only=True)
q = lambda sql: con.execute(sql).df()

# ----------------------------------------------------------------- extracts
log = q("SELECT * FROM audit.dq_issue_log")
log.to_csv(OUT / "dq_issue_log.csv", index=False)
recon = q("""SELECT recon_status, COUNT(*) AS merchant_days, ROUND(SUM(ABS(net_difference)), 2) AS abs_difference_inr
             FROM marts.rpt_settlement_reconciliation GROUP BY 1 ORDER BY 2 DESC""")
recon.to_csv(OUT / "reconciliation_summary.csv", index=False)
fee = q("""SELECT r.merchant_id, m.mdr_pct AS contracted_mdr_pct, ROUND(AVG(r.bank_implied_mdr_pct), 2) AS bank_implied_mdr_pct,
                  COUNT(*) AS days_affected, MIN(r.settlement_date) AS first_day, ROUND(SUM(r.exp_net - r.bank_net), 2) AS underpaid_inr
           FROM marts.rpt_settlement_reconciliation r JOIN marts.dim_merchants m USING (merchant_id)
           WHERE recon_status = 'fee_mismatch' GROUP BY 1, 2 ORDER BY 1""")
fee.to_csv(OUT / "fee_mismatch_by_merchant.csv", index=False)
q("SELECT * FROM marts.rpt_settlement_reconciliation WHERE recon_status <> 'matched' ORDER BY settlement_date").to_csv(
    OUT / "reconciliation_breaks.csv", index=False)
q("SELECT * FROM audit.dq_merchant_master_conflicts").to_csv(OUT / "merchant_master_conflicts.csv", index=False)

# ----------------------------------------------------------------- check the pipeline recovered the truth
truth = json.loads((ROOT / "data" / "truth.json").read_text())
got = con.execute("""SELECT COUNT(*) FILTER (WHERE status = 'captured'), ROUND(SUM(amount) FILTER (WHERE status = 'captured'), 2)
                     FROM marts.fct_payments""").fetchone()
checks = {
    "captured_payments": (truth["captured_payments"], int(got[0])),
    "captured_amount_inr": (truth["captured_amount"], float(got[1])),
    "refunds": (truth["refunds"], int(con.execute("SELECT COUNT(*) FROM marts.fct_refunds").fetchone()[0])),
    "chargebacks": (truth["chargebacks"], int(con.execute("SELECT COUNT(*) FROM marts.fct_chargebacks").fetchone()[0])),
    "settlements_missing_in_bank": (truth["bank_missing"], int(recon.set_index("recon_status").get("merchant_days").get("missing_in_bank_file", 0))),
    "bank_fee_errors": (truth["old_mdr_rows"], int(recon.set_index("recon_status")["merchant_days"].get("fee_mismatch", 0))),
}
ver = {k: {"expected": e, "pipeline": g, "ok": abs(float(e) - float(g)) < 0.01} for k, (e, g) in checks.items()}
(OUT / "verification.json").write_text(json.dumps(ver, indent=2))

raw_rows = sum(con.execute(f"SELECT COUNT(*) FROM raw.{t}").fetchone()[0] for t in ["gateway_payments", "legacy_pos_payments"])
summary = {
    "raw_payment_rows": int(raw_rows),
    "clean_payments": int(con.execute("SELECT COUNT(*) FROM marts.fct_payments").fetchone()[0]),
    "captured_value_cr": round(float(got[1]) / 1e7, 2),
    "merchants": int(con.execute("SELECT COUNT(*) FROM marts.dim_merchants").fetchone()[0]),
    "merchant_days_reconciled": int(recon["merchant_days"].sum()),
    "match_rate": round(float(recon.set_index("recon_status").loc["matched", "merchant_days"] / recon["merchant_days"].sum()), 4),
    "quarantined_records": int(con.execute("SELECT COUNT(*) FROM audit.dq_quarantine").fetchone()[0]),
    "missing_settlement_inr": float(recon.set_index("recon_status").loc["missing_in_bank_file", "abs_difference_inr"]),
    "fee_underpaid_inr": float(fee["underpaid_inr"].sum()),
    "legacy_rows_wrong_date_if_utc": int(log.loc[log["check_name"].str.startswith("Legacy IST timestamps that"), "rows_affected"].iloc[0]),
    "legacy_value_wrong_date_if_utc_inr": float(log.loc[log["check_name"].str.startswith("Legacy IST timestamps that"), "amount_affected"].iloc[0]),
    "all_verification_checks_pass": all(v["ok"] for v in ver.values()),
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

# ----------------------------------------------------------------- charts
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, NEUTRAL, ORANGE = "#2a78d6", "#c9c8c2", "#eb6834"
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                     "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "axes.axisbelow": True, "legend.frameon": False})

issues = log[log["source_table"] != "settlement_reconciliation"].copy()
issues = issues[~issues["check_name"].str.startswith("Local IST")]
issues["label"] = issues["check_name"].str.replace("Quarantined: ", "Quarantined: ", regex=False)
issues = issues.sort_values("rows_affected")
colors = [BLUE if s == "high" else (ORANGE if s == "medium" else NEUTRAL) for s in issues["severity"]]
fig, ax = plt.subplots(figsize=(10, 6.2))
ax.barh(issues["label"], issues["rows_affected"], color=colors, height=0.65)
ax.set_xscale("log")
for y, v in enumerate(issues["rows_affected"]):
    ax.text(v * 1.12, y, f"{v:,}", va="center", fontsize=9, color=INK)
ax.set_xlabel("Rows affected (log scale)")
ax.grid(axis="y", visible=False)
ax.set_xlim(0.8, 60000)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=BLUE, label="High severity"), Patch(color=ORANGE, label="Medium"), Patch(color=NEUTRAL, label="Low")],
          loc="lower right", fontsize=9)
ax.set_title("Data quality issues found in the raw extracts")
fig.tight_layout(); fig.savefig(CH / "dq_issues.png", dpi=170); plt.close(fig)

rb = recon[recon["recon_status"] != "matched"].sort_values("abs_difference_inr")
fig, ax = plt.subplots(figsize=(9, 2.9))
lab = rb["recon_status"].str.replace("_", " ").str.capitalize()
ax.barh(lab, rb["abs_difference_inr"] / 1e5, color=[BLUE if s == "missing_in_bank_file" else NEUTRAL for s in rb["recon_status"]], height=0.55)
for y, (v, n) in enumerate(zip(rb["abs_difference_inr"] / 1e5, rb["merchant_days"])):
    ax.text(v + 0.2, y, f"₹{v:,.2f} lakh  ({n} merchant-days)", va="center", fontsize=9)
ax.set_xlim(0, 30); ax.set_xlabel("Absolute difference (₹ lakh)"); ax.grid(axis="y", visible=False)
ax.set_title(f"Settlement reconciliation: {summary['match_rate']:.1%} matched; missing payouts are the biggest break")
fig.tight_layout(); fig.savefig(CH / "reconciliation_breaks.png", dpi=170); plt.close(fig)

# ----------------------------------------------------------------- lineage from dbt manifest
man = json.loads((ROOT / "dbt" / "target" / "manifest.json").read_text())
layer_color = {"source": "#e4e3df", "seed": "#e4e3df", "staging": "#cde2fb", "intermediate": "#9ec5f4",
               "marts": "#2a78d6", "audit": "#eb6834"}
nodes, edges = {}, set()
for uid, n in {**man["nodes"], **man["sources"]}.items():
    rt = n["resource_type"]
    if rt not in ("model", "seed", "source"):
        continue
    if rt == "source":
        name, layer = f"raw.{n['name']}", "source"
    elif rt == "seed":
        name, layer = n["name"], "seed"
    else:
        name, layer = n["name"], n["fqn"][1]
    nodes[uid] = (name, layer)
for uid, n in man["nodes"].items():
    if uid in nodes:
        for dep in n.get("depends_on", {}).get("nodes", []):
            if dep in nodes:
                edges.add((dep, uid))
dot = ["digraph G {", 'rankdir=LR; bgcolor="#fcfcfb"; nodesep=0.18; ranksep=0.9;',
       'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, color="#8a8984", penwidth=0.8];',
       'edge [color="#b9b8b2", arrowsize=0.6];']
for layer in ["source", "seed", "staging", "intermediate", "marts", "audit"]:
    members = [u for u, (_, l) in nodes.items() if l == layer]
    dot.append("{ rank=same; " + " ".join(f'"{u}";' for u in members) + " }" if layer not in ("seed", "audit") else "")
for u, (name, layer) in nodes.items():
    fc = "white" if layer in ("marts", "audit") else "#0b0b0b"
    dot.append(f'"{u}" [label="{name}", fillcolor="{layer_color[layer]}", fontcolor="{fc}"];')
for a, b in sorted(edges):
    dot.append(f'"{a}" -> "{b}";')
dot.append("}")
(OUT / "lineage.dot").write_text("\n".join(dot))
subprocess.run(["dot", "-Tpng", "-Gdpi=130", str(OUT / "lineage.dot"), "-o", str(CH / "lineage.png")], check=True)

print(json.dumps(summary, indent=2, default=str))
print(json.dumps(ver, indent=2))
