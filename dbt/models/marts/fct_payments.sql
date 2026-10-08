select payment_id, merchant_id, created_at_ist, payment_date, amount, currency, method,
       card_network, status, source_system
from {{ ref('int_payments_validated') }}
where dq_issue is null
