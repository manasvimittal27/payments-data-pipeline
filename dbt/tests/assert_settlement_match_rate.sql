-- Control threshold: at least 99% of merchant-day settlements must reconcile.
{{ config(severity = 'warn') }}
select match_rate
from (
    select avg(case when recon_status = 'matched' then 1.0 else 0 end) as match_rate
    from {{ ref('rpt_settlement_reconciliation') }}
)
where match_rate < 0.99
