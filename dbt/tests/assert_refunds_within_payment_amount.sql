-- Total valid refunds on a payment can never exceed what was paid.
select r.payment_id, sum(r.amount) as refunded, max(p.amount) as paid
from {{ ref('fct_refunds') }} r
join {{ ref('fct_payments') }} p using (payment_id)
group by r.payment_id
having sum(r.amount) > max(p.amount)
