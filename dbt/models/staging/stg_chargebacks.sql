select
    trim(chargeback_id)                         as chargeback_id,
    trim(payment_id)                            as payment_id,
    lower(trim(network))                        as network,
    nullif(trim(reason_code), '')               as reason_code,
    reason_code                                 as reason_code_raw,
    try_cast(amount as decimal(18, 2))          as amount,
    try_cast(received_date as date)             as received_date,
    lower(trim(stage))                          as stage
from {{ source('raw', 'chargebacks') }}
