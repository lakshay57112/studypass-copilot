# StudyPass: Risk, Fraud & Regulatory Intelligence Copilot

**Snowflake CoCo CLI Hackathon (GCC Edition) · Challenge: Risk, Fraud and Regulatory Intelligence Copilot**

**Live demo:** https://studypass-copilot.streamlit.app/ (demo mode on synthetic data, no login needed)

Every year Indian banks and NBFCs send billions of dollars abroad for students' education under the RBI
Liberalised Remittance Scheme (purpose code S0305), and they load student forex cards on top of that. Compliance teams
still check these by hand: LRS limits, who the money actually goes to, whether the student is still enrolled,
structuring below thresholds, odd card spend. Then they write STRs from scratch.

StudyPass is a copilot that runs inside Snowflake and is driven from **CoCo CLI**. It covers the full flow:

```
signal  ──►  evidence  ──►  documented finding / STR draft  ──►  human approval + audit log
(views)      (V_EVIDENCE)    (Cortex COMPLETE, cited)            (CASE_FINDINGS, AUDIT_LOG)
```

## What it does

| CoCo skill | What you type | What happens |
|---|---|---|
| `$risk-signal-scan` | `$risk-signal-scan who should we review first?` | Runs 7 governed signals, scores customers (POL-7), returns a ranked case queue |
| `$evidence-pack` | `$evidence-pack C0045` | Pulls every remittance, card txn and document behind each signal, with the policy clause |
| `$str-report` | `$str-report C0045` | Calls `SP_DRAFT_FINDING` (Cortex COMPLETE on governed facts only), checks cited IDs exist, saves the report, logs it, asks for approval |
| `$compliance-qa` | `$compliance-qa can we pay an education agent?` | Cortex Search over the policy KB + governed views, answers with clause citations |

### Signals (all in `sql/04_risk_signals.sql`)

| Signal | Policy | Weight |
|---|---|---|
| LRS limit breach (> USD 250k in a financial year) | POL-2.1 | 40 |
| Structuring: 3+ remittances of INR 9–10 lakh within 30 days | POL-5.2 | 30 |
| S0305 money paid to a third party (agents, trading firms) | POL-3.2 | 30 |
| Student enrolment withdrawn / unverified but remittances continue | POL-4.2 | 25 |
| Beneficiary country ≠ study country (flags high-risk jurisdictions) | POL-3.3 | 20 |
| Forex card at gambling / crypto / money-transfer merchants | POL-6.2 | 20 |
| Tuition paid > 120% of declared fee | POL-4.3 | 15 |

On the bundled synthetic data (400 families, 1.3k remittances, 6.7k card transactions, 46 injected fraud cases)
the signals catch **46/46 injected cases with zero false positives** (`data/ground_truth.csv`).

### Governed and explainable
- Analysts use the `COMPLIANCE_ANALYST` role: read-only views, PAN and account numbers masked (`MASK_PII`).
- Every signal row carries its evidence IDs and policy clause. Findings cite both.
- The LLM never queries data. It only writes the narrative from a fact bundle the procedure assembles, and the
  `$str-report` skill checks every evidence ID it cites.
- Every draft and decision is written to `AUDIT_LOG` (user, role, time). Findings stay `DRAFT_PENDING_REVIEW` until a human approves.

## Architecture

```
 Structured: CUSTOMERS · STUDENTS · REMITTANCES · CARD_TXNS · DOCUMENTS
 Unstructured: policy markdown ──► POLICY_CHUNKS ──► Cortex Search (POLICY_SEARCH)
                         │
                         ▼
        Governed views: V_SIG_* ─► V_RISK_SIGNALS ─► V_CUSTOMER_RISK, V_EVIDENCE
                         │
       ┌─────────────────┼──────────────────┬──────────────────┐
  $risk-signal-scan  $evidence-pack     $str-report        $compliance-qa
                                          │ SP_DRAFT_FINDING (Cortex COMPLETE)
                                          ▼
                              CASE_FINDINGS + AUDIT_LOG ─► Streamlit dashboard
```

## Run it

Prereqs: a Snowflake account (trial is fine) with Cortex enabled, and CoCo CLI (`cortex`) connected to it.

```bash
git clone https://github.com/<you>/studypass-copilot && cd studypass-copilot
cortex                       # start CoCo CLI in the repo root; skills in .cortex/skills load automatically
```

Then inside CoCo:

```
Run sql/01_setup.sql, sql/02_load_data.sql, sql/03_policies.sql, sql/04_risk_signals.sql, sql/05_findings.sql and sql/06_governance.sql in order against my account.
$risk-signal-scan who should we review first?
$evidence-pack C0045
$str-report C0045
$compliance-qa can we send S0305 money to an education agent?
```

If `PUT` is not supported by your client, load the CSVs with `python scripts/load_to_snowflake.py` instead of `02_load_data.sql`.

### Dashboard

```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py      # demo mode on bundled CSVs
```

The same app runs as **Streamlit in Snowflake** (upload `app/streamlit_app.py` and `app/engine.py`, plus the
`policies/` folder). There it reads the governed views and calls `SP_DRAFT_FINDING` and Cortex Search.

### Regenerate data
```bash
python scripts/generate_data.py && python scripts/build_policy_sql.py
```

## Repo layout
```
.cortex/skills/        4 CoCo CLI skills (risk-signal-scan, evidence-pack, str-report, compliance-qa)
sql/                   01 setup → 06 governance
policies/              illustrative education-remittance policy (source for Cortex Search)
data/                  synthetic CSVs + ground_truth.csv
app/                   Streamlit dashboard (Snowflake mode + demo mode) and pandas engine
scripts/               data generator, policy SQL builder, Python loader
docs/                  demo script
```

## Notes
All data is synthetic. The policy file paraphrases common Indian banking practice (RBI LRS, PMLA/FIU-IND) for the
prototype. It is not legal advice; check current RBI Master Directions before real use.

Built by Lakshay (solo) for the Snowflake CoCo CLI Hackathon, GCC Edition.
