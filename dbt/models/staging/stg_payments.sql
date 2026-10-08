-- One row per payment from both feeds, timestamps in IST, values standardised.
-- Deduplication: replayed batches (exact copies) and superseded status-update records are
-- collapsed to the latest, most-final status per payment_id.

with gateway as (
    select
        trim(payment_id)                                                        as payment_id,
        nullif(trim(merchant_id), '')                                           as merchant_id,
        -- gateway timestamps are UTC: convert to IST
        try_cast(replace(replace(created_at, 'T', ' '), 'Z', '') as timestamp)
            + interval 330 minute                                               as created_at_ist,
        try_cast(amount as decimal(18, 2))                                      as amount,
        upper(nullif(trim(currency), ''))                                       as currency_raw,
        lower(trim(method))                                                     as method,
        nullif(lower(trim(card_network)), '')                                   as card_network,
        lower(trim(status))                                                     as status,
        try_cast(replace(replace(ingested_at, 'T', ' '), 'Z', '') as timestamp) as ingested_at,
        'gateway'                                                               as source_system
    from {{ source('raw', 'gateway_payments') }}
),

legacy_pos as (
    select
        trim(txn_ref)                                                           as payment_id,
        nullif(trim(mid), '')                                                   as merchant_id,
        -- legacy terminals send local IST time: parse as-is, do NOT shift
        try_strptime(txn_time_local, '%d/%m/%Y %H:%M:%S')                       as created_at_ist,
        try_cast(amount_paise as bigint) / 100.0                                as amount,
        'INR'                                                                   as currency_raw,
        'card'                                                                  as method,
        nullif(lower(trim(network)), '')                                        as card_network,
        case upper(trim(txn_status)) when 'SUCCESS' then 'captured'
                                     when 'DECLINED' then 'failed' end           as status,
        cast(null as timestamp)                                                 as ingested_at,
        'legacy_pos'                                                            as source_system
    from {{ source('raw', 'legacy_pos_payments') }}
),

unioned as (
    select * from gateway
    union all
    select * from legacy_pos
),

ranked as (
    select *,
        row_number() over (
            partition by payment_id
            order by case status when 'captured' then 3 when 'failed' then 2 when 'authorized' then 1 else 0 end desc,
                     ingested_at desc nulls last
        ) as rn
    from unioned
)

select
    payment_id,
    merchant_id,
    created_at_ist,
    cast(created_at_ist as date)               as payment_date,
    amount,
    coalesce(currency_raw, 'INR')              as currency,          -- gateway is INR-only; blanks defaulted
    currency_raw is null                       as currency_defaulted,
    method,
    card_network,
    status,
    source_system
from ranked
where rn = 1
