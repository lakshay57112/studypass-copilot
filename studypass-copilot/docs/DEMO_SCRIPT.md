# Demo video script (3-4 min, screen recording)

Requirement: end-to-end workflow in CoCo CLI, Input → Processing → Output, 2-3 skills shown.
Record with OBS / Windows Game Bar (Win+Alt+R) / QuickTime. Upload to YouTube as **Unlisted** or Google Drive (anyone with link can view).

**Before recording:** run the setup once (step 0) so the recording isn't slowed by table creation. Increase terminal font size.

### 0. Setup (do before recording, not on video)
```
cd studypass-copilot
cortex
> Run sql/01_setup.sql through sql/06_governance.sql in order against my account.
```

### 1. Intro (0:00-0:20) - talk over the README
"Banks send education remittances abroad under LRS. Compliance checks them by hand. StudyPass is a CoCo CLI copilot
that goes from signal to evidence to an audit-ready STR draft, all inside Snowflake."

### 2. Skill 1 - signals (0:20-1:00)
```
/skill list
$risk-signal-scan who should we review first this week?
```
Point at: 7 signals, 46 customers flagged, ranked queue, each with a policy clause.

### 3. Skill 2 - evidence (1:00-1:50)
```
$evidence-pack C0045
```
(Use the top customer from step 2.) Point at: exact remittance IDs, amounts, policy text quoted.

### 4. Skill 3 - finding / STR (1:50-2:50)
```
$str-report C0045
```
Point at: Cortex-written narrative with [evidence IDs] and (clauses), the hallucination check, the row in CASE_FINDINGS
and the AUDIT_LOG entry. Approve it -> `SP_REVIEW_FINDING` runs.

### 5. Skill 4 - natural-language question (2:50-3:20)
```
$compliance-qa can we send S0305 money to an education agent, and which customers did that?
```

### 6. Close (3:20-3:40) - show the Streamlit dashboard
Overview → Case investigation → Draft finding → Audit trail. "Signal, evidence, finding, approval, audit. Thanks."
