-- Expected settlement (from our own data) vs what the bank paid, per merchant per day.
-- Expected net = captured - refunds - fees, fees = gross x MDR x 1.18 (18% GST), paid T+1.
with expected as (
    select
        d.merchant_id,
        d.business_date + interval 1 day                                             as settlement_date,
        d.captured_amount                                                             as exp_gross,
        d.refund_amount                                                               as exp_refunds,
        round(d.captured_amount * m.mdr_pct / 100 * 1.18, 2)                          as exp_fees
    from {{ ref('mart_merchant_daily') }} d
    join {{ ref('dim_merchants') }} m using (merchant_id)
    where d.captured_amount > 0 or d.refund_amount > 0
),
bank as (
    select merchant_id, settlement_date, gross_amount, refund_amount, fee_amount, net_amount
    from {{ ref('stg_bank_settlements') }}
)
select
    coalesce(e.merchant_id, b.merchant_id)                              as merchant_id,
    cast(coalesce(e.settlement_date, b.settlement_date) as date)        as settlement_date,
    e.exp_gross, e.exp_refunds, e.exp_fees,
    round(e.exp_gross - e.exp_refunds - e.exp_fees, 2)                  as exp_net,
    b.gross_amount as bank_gross, b.refund_amount as bank_refunds, b.fee_amount as bank_fees, b.net_amount as bank_net,
    round(coalesce(b.net_amount, 0) - coalesce(e.exp_gross - e.exp_refunds - e.exp_fees, 0), 2) as net_difference,
    case
        when b.merchant_id is null                                                  then 'missing_in_bank_file'
        when e.merchant_id is null                                                  then 'unexpected_in_bank_file'
        when abs(b.net_amount - (e.exp_gross - e.exp_refunds - e.exp_fees)) <= 1.00 then 'matched'
        when abs(b.gross_amount - e.exp_gross) > 1.00                               then 'gross_mismatch'
        when abs(b.fee_amount - e.exp_fees) > 1.00                                  then 'fee_mismatch'
        else 'other_mismatch'
    end                                                                 as recon_status,
    case when e.exp_gross > 0 and b.fee_amount is not null
         then round(b.fee_amount / e.exp_gross / 1.18 * 100, 3) end     as bank_implied_mdr_pct
from expected e
full outer join bank b
  on b.merchant_id = e.merchant_id and b.settlement_date = cast(e.settlement_date as date)
