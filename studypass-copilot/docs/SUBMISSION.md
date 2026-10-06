# Hack2skill submission fields

**Challenge:** Risk, Fraud and Regulatory Intelligence Copilot

**Prototype/MVP Brief (≤1024 chars):**
StudyPass is a CoCo CLI copilot for bank/NBFC compliance teams handling education remittances (RBI LRS, purpose S0305) and student forex cards. 7 governed SQL signals (LRS breach, structuring under INR 10L, third-party payees, country mismatch, inactive enrolment, fee inflation, gambling/crypto card spend) score customers by policy weights. 4 modular CoCo skills run the flow: $risk-signal-scan ranks cases, $evidence-pack pulls cited transactions, documents and policy clauses, $str-report drafts an audit-ready finding/STR with Cortex COMPLETE on governed facts only, checks cited IDs, stores it with an audit log and needs human approval, $compliance-qa answers NL questions via Cortex Search with clause citations. Masked PII, least-privilege role. On synthetic data (400 families, 8k txns) it caught 46/46 injected fraud cases with 0 false positives. Streamlit dashboard included.
