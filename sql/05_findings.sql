-- StudyPass | 05 Signal -> Evidence -> Finding (audit-ready STR draft with Cortex AI)
USE SCHEMA STUDYPASS.CORE;

-- Evidence pack: every transaction / document cited by a signal, flattened with its source row
CREATE OR REPLACE VIEW V_EVIDENCE AS
WITH X AS (
  SELECT S.CUSTOMER_ID, S.SIGNAL_CODE, S.POLICY_CLAUSE, E.VALUE::VARCHAR AS EVIDENCE_ID
  FROM V_RISK_SIGNALS S, LATERAL FLATTEN(INPUT => S.EVIDENCE_IDS) E
)
SELECT X.CUSTOMER_ID, X.SIGNAL_CODE, X.POLICY_CLAUSE, X.EVIDENCE_ID,
       COALESCE(
         IFF(R.REMITTANCE_ID IS NOT NULL,
             'Remittance ' || R.REMITTANCE_ID || ' on ' || R.TXN_DATE || ': USD ' || R.AMOUNT_USD || ' (INR ' || R.AMOUNT_INR || ') to '
             || R.BENEFICIARY_NAME || ' [' || R.BENEFICIARY_TYPE || ', ' || R.BENEFICIARY_COUNTRY || '], purpose ' || R.PURPOSE_CODE, NULL),
         IFF(T.TXN_ID IS NOT NULL,
             'Card txn ' || T.TXN_ID || ' at ' || T.TXN_TS || ': USD ' || T.AMOUNT_USD || ', MCC ' || T.MCC || ' ' || T.MCC_DESC || ' in ' || T.MERCHANT_COUNTRY, NULL),
         IFF(D.DOC_ID IS NOT NULL,
             'Document ' || D.DOC_ID || ': ' || D.DOC_TYPE || ', verified=' || D.VERIFIED || ', uploaded ' || D.UPLOADED_ON, NULL)
       ) AS EVIDENCE_TEXT
FROM X
LEFT JOIN REMITTANCES R ON R.REMITTANCE_ID = X.EVIDENCE_ID
LEFT JOIN CARD_TXNS   T ON T.TXN_ID        = X.EVIDENCE_ID
LEFT JOIN DOCUMENTS   D ON D.DOC_ID        = X.EVIDENCE_ID;

-- Draft a governed finding for one customer. Deterministic facts come from the views;
-- the LLM only writes the narrative and is told to use nothing else.
CREATE OR REPLACE PROCEDURE SP_DRAFT_FINDING(P_CUSTOMER_ID VARCHAR, P_MODEL VARCHAR DEFAULT 'mistral-large2')
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
AS
$$
import json

def run(session, p_customer_id, p_model):
    risk = session.sql("SELECT * FROM V_CUSTOMER_RISK WHERE CUSTOMER_ID = ?", params=[p_customer_id]).collect()
    if not risk:
        return {"customer_id": p_customer_id, "status": "NO_SIGNALS", "message": "No risk signals for this customer."}
    risk = risk[0].as_dict()
    signals = [r.as_dict() for r in session.sql(
        "SELECT SIGNAL_CODE, WEIGHT, DETAIL, POLICY_CLAUSE, EVIDENCE_IDS FROM V_RISK_SIGNALS WHERE CUSTOMER_ID = ? ORDER BY WEIGHT DESC",
        params=[p_customer_id]).collect()]
    evidence = [r.as_dict() for r in session.sql(
        "SELECT EVIDENCE_ID, EVIDENCE_TEXT FROM V_EVIDENCE WHERE CUSTOMER_ID = ? ORDER BY EVIDENCE_ID",
        params=[p_customer_id]).collect()]
    clauses = sorted({s["POLICY_CLAUSE"] for s in signals} | {"POL-7.2", "POL-8.1", "POL-8.2", "POL-8.3"})
    policy = [r.as_dict() for r in session.sql(
        "SELECT CLAUSE_ID, CLAUSE_TEXT FROM POLICY_CHUNKS WHERE ARRAY_CONTAINS(CLAUSE_ID::VARIANT, PARSE_JSON(?)) ORDER BY CLAUSE_ID",
        params=[json.dumps(clauses)]).collect()]
    kyc = session.sql("""SELECT C.CUSTOMER_NAME, C.CITY, C.SEGMENT, C.KYC_RISK_RATING, S.STUDENT_NAME, S.UNIVERSITY_NAME,
                                S.STUDY_COUNTRY, S.PROGRAM, S.ENROLMENT_STATUS, S.DECLARED_ANNUAL_FEE_USD
                         FROM CUSTOMERS C JOIN STUDENTS S ON S.CUSTOMER_ID = C.CUSTOMER_ID WHERE C.CUSTOMER_ID = ?""",
                      params=[p_customer_id]).collect()[0].as_dict()

    facts = {"customer_id": p_customer_id, "profile": kyc, "risk_score": risk["RISK_SCORE"], "risk_band": risk["RISK_BAND"],
             "signals": [{k: v for k, v in s.items() if k != "EVIDENCE_IDS"} for s in signals],
             "evidence": evidence, "policy": policy}
    prompt = (
        "You are a bank AML compliance assistant drafting an internal finding and Suspicious Transaction Report (STR) "
        "narrative for review by a human Compliance Analyst. Use ONLY the facts in the JSON below. Do not invent amounts, dates, "
        "names or IDs. Cite evidence IDs in square brackets, e.g. [R000123], and policy clauses in parentheses, e.g. (POL-3.2). "
        "Write these sections with markdown headings: 1. Summary, 2. Customer & student profile, 3. Red flags (one bullet per signal, "
        "with evidence IDs), 4. Policy assessment, 5. Recommendation (file STR / enhanced due diligence / close, with reason and the "
        "FIU-IND timeline), 6. Open questions for the reviewer. Keep it under 450 words. Mark the document 'DRAFT - pending analyst review'.\n\n"
        "FACTS:\n" + json.dumps(facts, default=str)
    )
    narrative = session.sql("SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?)", params=[p_model, prompt]).collect()[0][0]

    evidence_ids = [e["EVIDENCE_ID"] for e in evidence]
    session.sql("""INSERT INTO CASE_FINDINGS (CUSTOMER_ID, RISK_SCORE, RISK_BAND, SIGNALS, EVIDENCE_IDS, POLICY_CLAUSES, NARRATIVE)
                   SELECT ?, ?, ?, PARSE_JSON(?), PARSE_JSON(?), PARSE_JSON(?), ?""",
                params=[p_customer_id, risk["RISK_SCORE"], risk["RISK_BAND"], json.dumps([s["SIGNAL_CODE"] for s in signals]),
                        json.dumps(evidence_ids), json.dumps(clauses), narrative]).collect()
    session.sql("INSERT INTO AUDIT_LOG (ACTION, CUSTOMER_ID, DETAILS) SELECT 'DRAFT_FINDING', ?, PARSE_JSON(?)",
                params=[p_customer_id, json.dumps({"model": p_model, "signals": len(signals), "evidence": len(evidence_ids)})]).collect()
    return {"customer_id": p_customer_id, "risk_score": risk["RISK_SCORE"], "risk_band": risk["RISK_BAND"],
            "evidence_count": len(evidence_ids), "status": "DRAFT_PENDING_REVIEW", "narrative": narrative}
$$;

-- Human-in-the-loop approval (POL-8.3)
CREATE OR REPLACE PROCEDURE SP_REVIEW_FINDING(P_FINDING_ID VARCHAR, P_DECISION VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
  UPDATE CASE_FINDINGS SET STATUS = :P_DECISION, REVIEWED_BY = CURRENT_USER(), REVIEWED_AT = CURRENT_TIMESTAMP()
   WHERE FINDING_ID = :P_FINDING_ID;
  INSERT INTO AUDIT_LOG (ACTION, CUSTOMER_ID, DETAILS)
    SELECT 'REVIEW_FINDING', CUSTOMER_ID, OBJECT_CONSTRUCT('finding_id', FINDING_ID, 'decision', :P_DECISION)
    FROM CASE_FINDINGS WHERE FINDING_ID = :P_FINDING_ID;
  RETURN 'Finding ' || :P_FINDING_ID || ' marked ' || :P_DECISION;
END;
$$;

-- Try it on the highest-risk customer:
-- CALL SP_DRAFT_FINDING((SELECT CUSTOMER_ID FROM V_CUSTOMER_RISK ORDER BY RISK_SCORE DESC LIMIT 1));
