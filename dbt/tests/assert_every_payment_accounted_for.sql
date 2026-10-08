-- Completeness control: every deduplicated payment is either in fct_payments or in quarantine.
select s.payment_id
from {{ ref('stg_payments') }} s
left join {{ ref('fct_payments') }} f using (payment_id)
left join {{ ref('dq_quarantine') }} q on q.record_type = 'payment' and q.record_id = s.payment_id
where f.payment_id is null and q.record_id is null
