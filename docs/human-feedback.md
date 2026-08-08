# Human feedback and business outcomes

Import local JSONL with `modelswapbench outcomes summarize labels.jsonl`. Each
record supplies `case_id`, `model_alias`, and a label such as `accepted`,
`corrected`, `escalated`, `customer_reopened`, `human_override`, `unsafe`, or
`technically_correct_but_operationally_unusable`.

`business_success` is independent of API success. Reviewer roles and
pseudonymous IDs are optional; email addresses are rejected as reviewer IDs.
Aggregation reports acceptance, correction, escalation, reopen, override,
business success, and Decimal-based estimated cost per successful outcome.
The Python `compare_outcomes` API reports candidate-minus-baseline differences
without converting unknown values to zero.
