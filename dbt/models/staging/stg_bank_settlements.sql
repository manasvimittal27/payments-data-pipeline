-- Bank settlement file. Exact duplicate lines (same merchant, date and amounts) are collapsed.
with typed as (
    select
        try_cast(settlement_date as date)            as settlement_date,
        trim(merchant_id)                            as merchant_id,
        try_cast(gross_amount as decimal(18, 2))     as gross_amount,
        try_cast(refund_amount as decimal(18, 2))    as refund_amount,
        try_cast(fee_amount as decimal(18, 2))       as fee_amount,
        try_cast(net_amount as decimal(18, 2))       as net_amount,
        trim(utr)                                    as utr
    from {{ source('raw', 'bank_settlements') }}
)
select * exclude (rn)
from (
    select *, row_number() over (partition by merchant_id, settlement_date, gross_amount, net_amount order by utr) as rn
    from typed
)
where rn = 1
