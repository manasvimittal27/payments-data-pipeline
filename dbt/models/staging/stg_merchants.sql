-- Merchant master from the AUTHORITATIVE source (onboarding system).
select
    trim(merchant_id)                          as merchant_id,
    trim(legal_name)                           as legal_name,
    lower(trim(category))                      as category,
    cast(mdr_pct as decimal(5, 2))             as mdr_pct,
    cast(onboarded_on as date)                 as onboarded_on,
    lower(trim(status))                        as status
from {{ source('raw', 'merchants_onboarding') }}
