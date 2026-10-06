---
name: compliance-qa
description: Answer natural-language compliance and policy questions about education remittances, LRS, structuring, forex cards and STR rules with cited policy clauses (Cortex Search) and, when the question is about customers or amounts, governed data from the StudyPass views.
---

# Compliance Q&A (StudyPass)

## Rules
- Policy answers come only from Cortex Search service `STUDYPASS.CORE.POLICY_SEARCH`. Cite clause IDs like (POL-3.2).
- Data answers come only from `V_RISK_SIGNALS`, `V_CUSTOMER_RISK`, `V_SIGNAL_SUMMARY`, `V_EVIDENCE`. Show the SQL you ran.
- If neither source answers the question, say so and suggest escalation. Never guess regulatory facts.

## Steps
1. Retrieve clauses:
   ```sql
   SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
     'STUDYPASS.CORE.POLICY_SEARCH',
     '{"query": "<question>", "columns": ["CLAUSE_ID","CLAUSE_TEXT"], "limit": 4}'
   ))['results'];
   ```
2. If the question asks "who / which / how many / how much", also query the governed views.
3. Answer in 2-5 sentences with clause citations, then list the clauses used and any SQL run.
