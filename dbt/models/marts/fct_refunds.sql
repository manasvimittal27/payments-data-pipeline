select refund_id, payment_id, merchant_id, refunded_at_ist, cast(refunded_at_ist as date) as refund_date, amount
from {{ ref('int_refunds_validated') }}
where dq_issue is null
