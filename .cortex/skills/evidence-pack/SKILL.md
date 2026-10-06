---
name: evidence-pack
description: Build an explainable evidence pack for one customer - every signal, the exact remittances, card transactions and documents behind it, and the policy clauses that apply. Use when the user asks why a customer is flagged or wants to investigate a case.
---

# Evidence pack (StudyPass)

Input: a customer ID such as `C0045`. If none is given, take the top row of `V_CUSTOMER_RISK`.

## Rules
- Use `STUDYPASS.CORE` only. Read-only.
- Every red flag must cite evidence IDs (R..., T..., D...) and one policy clause. If something is not in the data, say "not in evidence".

## Steps
1. Profile:
   ```sql
   SELECT C.CUSTOMER_ID, C.CUSTOMER_NAME, C.CITY, C.SEGMENT, C.KYC_RISK_RATING,
          S.STUDENT_NAME, S.UNIVERSITY_NAME, S.STUDY_COUNTRY, S.PROGRAM, S.ENROLMENT_STATUS, S.DECLARED_ANNUAL_FEE_USD
   FROM STUDYPASS.CORE.CUSTOMERS C JOIN STUDYPASS.CORE.STUDENTS S USING (CUSTOMER_ID)
   WHERE C.CUSTOMER_ID = '<ID>';
   ```
2. Signals: `SELECT SIGNAL_CODE, WEIGHT, DETAIL, POLICY_CLAUSE FROM STUDYPASS.CORE.V_RISK_SIGNALS WHERE CUSTOMER_ID = '<ID>' ORDER BY WEIGHT DESC;`
3. Evidence: `SELECT SIGNAL_CODE, EVIDENCE_ID, EVIDENCE_TEXT FROM STUDYPASS.CORE.V_EVIDENCE WHERE CUSTOMER_ID = '<ID>' ORDER BY SIGNAL_CODE, EVIDENCE_ID;`
4. Policy text for the cited clauses:
   `SELECT CLAUSE_ID, CLAUSE_TEXT FROM STUDYPASS.CORE.POLICY_CHUNKS WHERE CLAUSE_ID IN (<clauses from step 2>, 'POL-7.2');`
5. Output a markdown evidence pack:
   - Header: customer, score, band.
   - Section per signal: what happened (DETAIL), evidence lines with IDs, the clause quoted.
   - "Not explained by data": anything the analyst must still check (e.g. other-bank LRS usage, university authorisation letters).
   - Next step: `$str-report <ID>`.
