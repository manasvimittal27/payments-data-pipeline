-- One row per data quality check: what was found, how much money it touches, and what the
-- pipeline does about it. This is the table behind the data quality report.

with raw_gw as (select * from {{ source('raw', 'gateway_payments') }}),

checks as (

    select 'gateway_payments' as source_table, 'Replayed batch: exact duplicate rows' as check_name,
           count(*) - count(distinct (payment_id, merchant_id, created_at, amount, status, ingested_at)) as rows_affected,
           null::decimal(18,2) as amount_affected, 'medium' as severity,
           'Collapsed to one row in staging' as pipeline_action
    from raw_gw

    union all
    select 'gateway_payments', 'Superseded status-update records (authorized before captured)',
           count(*) filter (where lower(status) = 'authorized'), null, 'low',
           'Latest, most-final status kept per payment'
    from raw_gw

    union all
    select 'gateway_payments', 'Currency blank or wrongly formatted',
           count(*) filter (where currency is null or currency <> 'INR'), null, 'low',
           'Trimmed and upper-cased; blanks defaulted to INR (gateway is INR-only)'
    from raw_gw

    union all
    select 'gateway_payments', 'Payment method in inconsistent case',
           count(*) filter (where method <> lower(method)), null, 'low', 'Lower-cased'
    from raw_gw

    union all
    select 'legacy_pos_payments', 'Local IST timestamps in a different format from the gateway',
           count(*), null, 'high',
           'Parsed as IST, not shifted; treating them as UTC would move these to the wrong business date'
    from {{ source('raw', 'legacy_pos_payments') }}

    union all
    select 'legacy_pos_payments', 'Legacy IST timestamps that would shift date if read as UTC',
           count(*) filter (where hour(try_strptime(txn_time_local, '%d/%m/%Y %H:%M:%S')) * 60
                                 + minute(try_strptime(txn_time_local, '%d/%m/%Y %H:%M:%S')) >= 18 * 60 + 30),
           sum(try_cast(amount_paise as bigint) / 100.0) filter (
               where hour(try_strptime(txn_time_local, '%d/%m/%Y %H:%M:%S')) * 60
                   + minute(try_strptime(txn_time_local, '%d/%m/%Y %H:%M:%S')) >= 18 * 60 + 30),
           'high', 'Avoided by correct parsing (IST 18:30 or later = next day in IST-as-UTC+5:30 shift)'
    from {{ source('raw', 'legacy_pos_payments') }}

    union all
    select 'payments', 'Quarantined: ' || replace(dq_issue, '_', ' '), count(*), sum(amount), 'high',
           'Held in dq_quarantine; excluded from marts'
    from {{ ref('int_payments_validated') }} where dq_issue is not null group by dq_issue

    union all
    select 'refunds', 'Quarantined: ' || replace(dq_issue, '_', ' '), count(*), sum(amount), 'high',
           'Held in dq_quarantine; raise with refund system owner'
    from {{ ref('int_refunds_validated') }} where dq_issue is not null group by dq_issue

    union all
    select 'chargebacks', 'Unrecognised reason code', count(*) filter (where not reason_code_valid),
           sum(amount) filter (where not reason_code_valid), 'medium',
           'Kept and flagged; request corrected code from the network feed'
    from {{ ref('fct_chargebacks') }}

    union all
    select 'merchant_master',
           case conflict_type when 'category_conflict' then 'CRM category differs from onboarding system'
                              when 'in_crm_only' then 'Merchant in CRM but not in onboarding system'
                              else 'Merchant missing from CRM' end, count(*), null, 'medium',
           'Onboarding system used as authoritative source'
    from {{ ref('dq_merchant_master_conflicts') }} group by conflict_type

    union all
    select 'bank_settlements', 'Duplicate settlement lines', 
           (select count(*) from {{ source('raw', 'bank_settlements') }}) - (select count(*) from {{ ref('stg_bank_settlements') }}),
           null, 'high', 'Collapsed; confirm with bank that payment was not made twice'

    union all
    select 'settlement_reconciliation', 'Settlement ' || replace(recon_status, '_', ' '), count(*),
           sum(abs(net_difference)), case when recon_status = 'matched' then 'info' else 'high' end,
           case recon_status
                when 'matched' then 'No action'
                when 'missing_in_bank_file' then 'Chase bank for unpaid settlement'
                when 'unexpected_in_bank_file' then 'Investigate: bank paid a merchant we have no record of'
                when 'fee_mismatch' then 'Bank fee differs from contracted MDR: raise pricing dispute'
                else 'Investigate difference' end
    from {{ ref('rpt_settlement_reconciliation') }} group by recon_status
)

select * from checks where rows_affected > 0
order by case severity when 'high' then 1 when 'medium' then 2 when 'low' then 3 else 4 end, source_table, check_name
