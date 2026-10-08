-- Daily merchant performance: the table dashboards and reports read from.
with pay as (
    select merchant_id, payment_date as d,
           count(*) filter (where status = 'captured')               as captured_count,
           sum(amount) filter (where status = 'captured')            as captured_amount,
           count(*) filter (where status = 'failed')                 as failed_count
    from {{ ref('fct_payments') }} group by all
), ref as (
    select merchant_id, refund_date as d, count(*) as refund_count, sum(amount) as refund_amount
    from {{ ref('fct_refunds') }} group by all
), cb as (
    select merchant_id, received_date as d, count(*) as chargeback_count
    from {{ ref('fct_chargebacks') }} where merchant_id is not null group by all
)
select
    merchant_id, d as business_date,
    coalesce(captured_count, 0)                                         as captured_count,
    coalesce(captured_amount, 0)                                        as captured_amount,
    coalesce(failed_count, 0)                                           as failed_count,
    round(coalesce(failed_count, 0) / nullif(coalesce(captured_count, 0) + coalesce(failed_count, 0), 0), 4) as failure_rate,
    coalesce(refund_count, 0)                                           as refund_count,
    coalesce(refund_amount, 0)                                          as refund_amount,
    coalesce(chargeback_count, 0)                                       as chargeback_count
from pay
full outer join ref using (merchant_id, d)
full outer join cb using (merchant_id, d)
