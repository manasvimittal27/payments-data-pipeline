-- Totals must not change between layers: captured amount in fct_payments = sum of the daily mart.
select f.total as fct_total, d.total as mart_total
from (select sum(amount) as total from {{ ref('fct_payments') }} where status = 'captured') f,
     (select sum(captured_amount) as total from {{ ref('mart_merchant_daily') }}) d
where abs(f.total - d.total) > 0.01
