-- Merchant attributes where the CRM disagrees with the authoritative onboarding system.
select
    coalesce(o.merchant_id, c.merchant_id)                  as merchant_id,
    o.category                                              as onboarding_category,
    c.category                                              as crm_category,
    case when o.merchant_id is null then 'in_crm_only'
         when c.merchant_id is null then 'missing_from_crm'
         else 'category_conflict' end                       as conflict_type,
    'onboarding system'                                     as authoritative_source
from {{ ref('stg_merchants') }} o
full outer join {{ ref('stg_merchants_crm') }} c using (merchant_id)
where o.merchant_id is null or c.merchant_id is null or o.category <> c.category
