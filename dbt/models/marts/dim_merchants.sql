select
    m.*,
    c.category is not null and c.category <> m.category as crm_category_conflict
from {{ ref('stg_merchants') }} m
left join {{ ref('stg_merchants_crm') }} c using (merchant_id)
