{# Generic test: every value in the column must be greater than zero. #}
{% test positive(model, column_name) %}
select * from {{ model }} where {{ column_name }} <= 0
{% endtest %}
