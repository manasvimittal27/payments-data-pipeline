-- Every record held back from the marts, with the reason. Nothing is dropped silently.
select 'payment' as record_type, payment_id as record_id, merchant_id, amount, dq_issue, source_system
from {{ ref('int_payments_validated') }} where dq_issue is not null
union all
select 'refund', refund_id, merchant_id, amount, dq_issue, 'refunds'
from {{ ref('int_refunds_validated') }} where dq_issue is not null
