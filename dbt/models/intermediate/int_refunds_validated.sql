with r as (
    select
        r.*,
        p.amount                               as payment_amount,
        p.status                               as payment_status,
        p.created_at_ist                       as payment_at_ist,
        p.merchant_id,
        sum(r.amount) over (partition by r.payment_id order by r.refunded_at_ist, r.refund_id
                            rows between unbounded preceding and current row) as cumulative_refunded,
        row_number() over (partition by r.payment_id, r.refunded_at_ist order by r.refund_id) as same_time_seq
    from {{ ref('stg_refunds') }} r
    left join {{ ref('fct_payments') }} p using (payment_id)
)
select
    *,
    case
        when payment_amount is null                 then 'orphan_refund_no_payment'
        when payment_status <> 'captured'           then 'refund_on_uncaptured_payment'
        when amount is null or amount <= 0          then 'invalid_refund_amount'
        when cumulative_refunded > payment_amount   then 'refund_exceeds_payment'
        when same_time_seq > 1                      then 'possible_duplicate_refund'
        when refunded_at_ist < payment_at_ist       then 'refund_before_payment'
    end as dq_issue
from r
