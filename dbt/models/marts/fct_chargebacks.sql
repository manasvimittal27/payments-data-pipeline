-- Chargebacks are real money movements, so rows with an unrecognised reason code are kept
-- and flagged rather than quarantined.
select
    c.chargeback_id, c.payment_id, p.merchant_id, c.network, c.reason_code, c.amount, c.received_date, c.stage,
    coalesce(rc.reason_group, 'unrecognised_code')  as reason_group,
    rc.reason_code is not null                      as reason_code_valid
from {{ ref('stg_chargebacks') }} c
left join {{ ref('fct_payments') }} p using (payment_id)
left join {{ ref('chargeback_reason_codes') }} rc
       on rc.network = c.network and cast(rc.reason_code as varchar) = c.reason_code
