---
name: str-report
description: Turn a flagged case into an audit-ready documented finding and draft Suspicious Transaction Report (STR) narrative using Cortex AI, store it in CASE_FINDINGS with an audit log entry, and export it as markdown. Use when the user asks to document, report, or draft an STR for a customer.
---

# STR / finding report (StudyPass)

Input: a customer ID. The report is a DRAFT until a human approves it (POL-8.3).

## Steps
1. Draft and store the finding (Cortex COMPLETE inside the procedure only sees governed facts):
   ```sql
   CALL STUDYPASS.CORE.SP_DRAFT_FINDING('<ID>');
   ```
   If the default model is not available in the region, call `SP_DRAFT_FINDING('<ID>', 'llama3.1-70b')`.
2. Show the `narrative` field from the result as formatted markdown.
3. Verify it: every evidence ID in the narrative must exist in
   `SELECT EVIDENCE_ID FROM STUDYPASS.CORE.V_EVIDENCE WHERE CUSTOMER_ID = '<ID>'`. List any ID that does not match as a hallucination warning.
4. Save the narrative to `reports/finding_<ID>.md` in the working directory.
5. Show the stored row and audit entry:
   ```sql
   SELECT FINDING_ID, CUSTOMER_ID, RISK_BAND, STATUS, CREATED_BY, CREATED_AT FROM STUDYPASS.CORE.CASE_FINDINGS WHERE CUSTOMER_ID = '<ID>' ORDER BY CREATED_AT DESC LIMIT 1;
   SELECT EVENT_TS, ACTOR, ROLE_NAME, ACTION, DETAILS FROM STUDYPASS.CORE.AUDIT_LOG WHERE CUSTOMER_ID = '<ID>' ORDER BY EVENT_TS DESC LIMIT 5;
   ```
6. Ask the user whether to approve. On approval run
   `CALL STUDYPASS.CORE.SP_REVIEW_FINDING('<FINDING_ID>', 'APPROVED_FOR_STR');` (or `'CLOSED_FALSE_POSITIVE'`).
   Remind them the STR goes to FIU-IND within 7 working days of the conclusion (POL-8.1) and must not be disclosed to the customer (POL-8.2).
