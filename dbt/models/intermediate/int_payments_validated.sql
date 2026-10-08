-- Validate each payment against business rules. Invalid rows are kept and labelled,
-- never silently dropped: marts take the valid rows, the audit layer takes the rest.
select
    p.*,
    case
        when p.merchant_id is null                 then 'missing_merchant_id'
        when m.merchant_id is null                 then 'unknown_merchant_id'
        when p.amount is null                      then 'unparseable_amount'
        when p.amount <= 0                         then 'non_positive_amount'
        when p.created_at_ist is null              then 'unparseable_timestamp'
        when p.status not in ('captured', 'failed') then 'unexpected_status'
    end as dq_issue
from {{ ref('stg_payments') }} p
left join {{ ref('stg_merchants') }} m using (merchant_id)
