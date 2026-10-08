-- CRM copy of merchant data: NOT authoritative, kept only to detect conflicts.
select
    trim(merchant_id)      as merchant_id,
    trim(legal_name)       as legal_name,
    lower(trim(category))  as category
from {{ source('raw', 'merchants_crm') }}
