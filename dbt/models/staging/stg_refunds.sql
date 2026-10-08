select
    trim(refund_id)                                                             as refund_id,
    trim(payment_id)                                                            as payment_id,
    try_cast(replace(replace(created_at, 'T', ' '), 'Z', '') as timestamp)
        + interval 330 minute                                                   as refunded_at_ist,
    try_cast(amount as decimal(18, 2))                                          as amount,
    lower(trim(status))                                                         as status
from {{ source('raw', 'refunds') }}
