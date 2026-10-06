"""
StudyPass - Risk, Fraud & Regulatory Intelligence Copilot for education remittances.

Runs two ways:
  * Streamlit in Snowflake: reads governed views (V_RISK_SIGNALS, V_CUSTOMER_RISK, V_EVIDENCE),
    drafts findings with SP_DRAFT_FINDING (Cortex COMPLETE) and answers policy questions with Cortex Search.
  * Anywhere else (local / Streamlit Community Cloud): same logic on the bundled synthetic CSVs.
"""
import json
import os
import sys
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(__file__))
import engine  # noqa: E402

st.set_page_config(page_title="StudyPass Copilot", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
h1, h2, h3 {letter-spacing: -0.01em;}
.sp-badge {display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;}
.sp-HIGH {background:#fde8e8;color:#b42318;} .sp-MEDIUM {background:#fef3c7;color:#92400e;} .sp-LOW {background:#e7f5ec;color:#166534;}
.sp-muted {color:#6b7280;font-size:13px;}
</style>
""", unsafe_allow_html=True)

# ---------- data access ----------
try:
    from snowflake.snowpark.context import get_active_session
    SESSION = get_active_session()
    MODE = "snowflake"
except Exception:
    SESSION = None
    MODE = "demo"


@st.cache_data(show_spinner=False)
def demo_state():
    dfs = engine.load_data()
    sig = engine.compute_signals(dfs)
    risk = engine.customer_risk(sig, dfs["customers"])
    return dfs, sig, risk, engine.load_policy()


def q(sql, params=None):
    return SESSION.sql(sql, params=params).to_pandas()


if MODE == "snowflake":
    SESSION.sql("USE SCHEMA STUDYPASS.CORE").collect()
    signals = q("SELECT * FROM V_RISK_SIGNALS")
    signals["EVIDENCE_IDS"] = signals["EVIDENCE_IDS"].map(json.loads)
    risk = q("SELECT * FROM V_CUSTOMER_RISK ORDER BY RISK_SCORE DESC")
    for col in ["SIGNALS", "POLICY_CLAUSES"]:
        risk[col] = risk[col].map(json.loads)
    remit = q("SELECT AMOUNT_USD, TXN_DATE FROM REMITTANCES")
    n_customers = q("SELECT COUNT(*) N FROM CUSTOMERS")["N"][0]
else:
    dfs, signals, risk, policy = demo_state()
    remit = dfs["remittances"]
    n_customers = len(dfs["customers"])

if "findings" not in st.session_state:
    st.session_state.findings = []
if "audit" not in st.session_state:
    st.session_state.audit = []


def audit(action, cid, details):
    st.session_state.audit.append({"EVENT_TS": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ACTION": action,
                                   "CUSTOMER_ID": cid, "DETAILS": json.dumps(details)})


# ---------- header ----------
left, right = st.columns([3, 1])
with left:
    st.title("StudyPass")
    st.caption("Risk, fraud & regulatory copilot for education remittances (LRS · S0305) and student forex cards")
with right:
    st.markdown(f"<div style='text-align:right' class='sp-muted'><br>Mode: <b>{'Snowflake (governed views + Cortex)' if MODE == 'snowflake' else 'Demo (synthetic data)'}</b></div>",
                unsafe_allow_html=True)

tab_overview, tab_cases, tab_ask, tab_audit = st.tabs(["Overview", "Case investigation", "Ask the copilot", "Audit trail"])

# ---------- overview ----------
with tab_overview:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Customers monitored", f"{n_customers:,}")
    k2.metric("Education remittances", f"USD {remit['AMOUNT_USD'].sum() / 1e6:,.1f}M")
    k3.metric("Customers flagged", f"{risk['CUSTOMER_ID'].nunique()}")
    k4.metric("High-risk cases", f"{(risk['RISK_BAND'] == 'HIGH').sum()}")
    st.caption(f"{len(remit):,} remittances · {len(signals)} signals raised · scoring per POL-7.1 (≥40 HIGH, 20–39 MEDIUM)")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader("Signals by type")
        summ = (signals.groupby(["SIGNAL_CODE", "POLICY_CLAUSE"]).agg(CUSTOMERS=("CUSTOMER_ID", "nunique"))
                .reset_index().sort_values("CUSTOMERS", ascending=False))
        summ["SIGNAL"] = summ["SIGNAL_CODE"].map(engine.SIGNAL_LABEL)
        st.altair_chart(alt.Chart(summ).mark_bar(color="#2563eb", cornerRadiusEnd=3).encode(
            x=alt.X("CUSTOMERS:Q", title="Customers flagged"), y=alt.Y("SIGNAL:N", sort="-x", title=None,
            axis=alt.Axis(labelLimit=260)), tooltip=["SIGNAL", "POLICY_CLAUSE", "CUSTOMERS"]).properties(height=280),
            use_container_width=True)
    with c2:
        st.subheader("Risk bands")
        bands = risk["RISK_BAND"].value_counts().reindex(["HIGH", "MEDIUM", "LOW"]).fillna(0).astype(int).reset_index()
        bands.columns = ["BAND", "CUSTOMERS"]
        st.altair_chart(alt.Chart(bands).mark_bar(cornerRadiusEnd=3).encode(
            x=alt.X("CUSTOMERS:Q", title="Customers"), y=alt.Y("BAND:N", sort=["HIGH", "MEDIUM", "LOW"], title=None),
            color=alt.Color("BAND:N", scale=alt.Scale(domain=["HIGH", "MEDIUM", "LOW"], range=["#b42318", "#d97706", "#16a34a"]), legend=None),
            tooltip=["BAND", "CUSTOMERS"]).properties(height=280), use_container_width=True)

# ---------- cases ----------
with tab_cases:
    st.subheader("1 · Signal → case queue")
    fc1, fc2 = st.columns([1, 2])
    band_f = fc1.multiselect("Risk band", ["HIGH", "MEDIUM", "LOW"], default=["HIGH", "MEDIUM"])
    sig_f = fc2.multiselect("Signal", list(engine.SIGNAL_LABEL), format_func=engine.SIGNAL_LABEL.get)
    queue = risk[risk["RISK_BAND"].isin(band_f)]
    if sig_f:
        queue = queue[queue["SIGNALS"].map(lambda s: bool(set(s) & set(sig_f)))]
    show = queue[["CUSTOMER_ID", "CUSTOMER_NAME", "CITY", "RISK_SCORE", "RISK_BAND", "SIGNALS"]].copy()
    show["SIGNALS"] = show["SIGNALS"].map(lambda s: ", ".join(engine.SIGNAL_LABEL.get(x, x) for x in s))
    st.dataframe(show, hide_index=True, height=260)

    if queue.empty:
        st.info("No cases match these filters.")
    else:
        cid = st.selectbox("Open case", queue["CUSTOMER_ID"],
                           format_func=lambda c: f"{c} · {risk.set_index('CUSTOMER_ID').loc[c, 'CUSTOMER_NAME']} · score {risk.set_index('CUSTOMER_ID').loc[c, 'RISK_SCORE']}")
        row = risk.set_index("CUSTOMER_ID").loc[cid]
        st.markdown(f"#### {row['CUSTOMER_NAME']} <span class='sp-badge sp-{row['RISK_BAND']}'>{row['RISK_BAND']} · {row['RISK_SCORE']}</span>",
                    unsafe_allow_html=True)

        st.subheader("2 · Evidence")
        csig = signals[signals["CUSTOMER_ID"] == cid].sort_values("WEIGHT", ascending=False)
        for _, s in csig.iterrows():
            st.markdown(f"**{engine.SIGNAL_LABEL[s['SIGNAL_CODE']]}** · +{s['WEIGHT']} · `{s['POLICY_CLAUSE']}`  \n{s['DETAIL']}")
        if MODE == "snowflake":
            ev = q("SELECT SIGNAL_CODE, POLICY_CLAUSE, EVIDENCE_ID, EVIDENCE_TEXT FROM V_EVIDENCE WHERE CUSTOMER_ID = ?", [cid])
        else:
            ev = engine.evidence_for(cid, signals, dfs)
        with st.expander(f"Evidence records ({len(ev)})", expanded=False):
            st.dataframe(ev, hide_index=True)

        st.subheader("3 · Documented finding")
        if st.button("Draft audit-ready finding", type="primary"):
            with st.spinner("Assembling signals, evidence and policy clauses…"):
                if MODE == "snowflake":
                    res = json.loads(SESSION.sql("CALL SP_DRAFT_FINDING(?)", params=[cid]).collect()[0][0])
                    text = res.get("narrative", res.get("message", ""))
                else:
                    text = engine.draft_finding(cid, signals, risk, dfs, policy)
                    audit("DRAFT_FINDING", cid, {"signals": len(csig), "evidence": len(ev), "engine": "template"})
                st.session_state.findings.append({"CUSTOMER_ID": cid, "STATUS": "DRAFT_PENDING_REVIEW", "NARRATIVE": text})
        drafts = [f for f in st.session_state.findings if f["CUSTOMER_ID"] == cid]
        if drafts:
            f = drafts[-1]
            st.markdown(f["NARRATIVE"])
            b1, b2, b3 = st.columns(3)
            b1.download_button("Download finding (.md)", f["NARRATIVE"], file_name=f"StudyPass_finding_{cid}.md")
            if b2.button("Approve for STR filing"):
                f["STATUS"] = "APPROVED_FOR_STR"
                audit("REVIEW_FINDING", cid, {"decision": "APPROVED_FOR_STR"})
                st.success("Approved. Logged to audit trail.")
            if b3.button("Close as false positive"):
                f["STATUS"] = "CLOSED_FALSE_POSITIVE"
                audit("REVIEW_FINDING", cid, {"decision": "CLOSED_FALSE_POSITIVE"})
                st.info("Closed. Logged to audit trail.")

# ---------- ask ----------
with tab_ask:
    st.subheader("Ask a compliance question")
    st.markdown("<span class='sp-muted'>Answers come only from the policy knowledge base and governed views, with clause citations.</span>",
                unsafe_allow_html=True)
    examples = ["Can we send S0305 money to an education agent?", "What is the LRS limit and what happens on breach?",
                "How fast must an STR be filed?", "Which customers are structuring remittances?"]
    qtext = st.text_input("Question", placeholder=examples[0])
    st.caption("Try: " + " · ".join(examples))
    if qtext:
        lower = qtext.lower()
        data_q = next((code for code, kw in [("STRUCTURING", "structur"), ("LRS_BREACH", "breach"), ("THIRD_PARTY_BENEFICIARY", "third"),
                                            ("CARD_RISKY_MCC", "card"), ("COUNTRY_MISMATCH", "country"), ("INACTIVE_ENROLMENT", "enrol"),
                                            ("FEE_INFLATION", "fee")] if kw in lower and ("customer" in lower or "who" in lower or "which" in lower)), None)
        if data_q:
            hits = signals[signals["SIGNAL_CODE"] == data_q][["CUSTOMER_ID", "DETAIL", "POLICY_CLAUSE"]]
            st.markdown(f"**{len(hits)} customer(s)** have the *{engine.SIGNAL_LABEL[data_q]}* signal (source: `V_RISK_SIGNALS`).")
            st.dataframe(hits, hide_index=True)
        elif MODE == "snowflake":
            hits = SESSION.sql(
                "SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('STUDYPASS.CORE.POLICY_SEARCH', ?))['results'] R",
                params=[json.dumps({"query": qtext, "columns": ["CLAUSE_ID", "CLAUSE_TEXT"], "limit": 4})]).collect()[0][0]
            ctx = json.loads(hits)
            prompt = ("Answer the compliance question using ONLY these policy clauses. Cite clause IDs in parentheses. "
                      "If the clauses do not answer it, say so.\nCLAUSES: " + json.dumps(ctx) + "\nQUESTION: " + qtext)
            ans = SESSION.sql("SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', ?)", params=[prompt]).collect()[0][0]
            st.markdown(ans)
            st.dataframe(pd.DataFrame(ctx), hide_index=True)
        else:
            hits = engine.search_policy(qtext, policy)
            if hits.empty:
                st.warning("No policy clause matches this question. Escalate to Compliance.")
            else:
                top = hits.iloc[0]
                st.markdown(f"**Answer (from {top['CLAUSE_ID']}):** {top['CLAUSE_TEXT']}")
                st.markdown("**Related clauses**")
                for _, h in hits.iloc[1:].iterrows():
                    st.markdown(f"- ({h['CLAUSE_ID']}) {h['CLAUSE_TEXT']}")

# ---------- audit ----------
with tab_audit:
    st.subheader("Audit trail")
    if MODE == "snowflake":
        st.dataframe(q("SELECT * FROM AUDIT_LOG ORDER BY EVENT_TS DESC LIMIT 200"), hide_index=True)
        st.dataframe(q("SELECT FINDING_ID, CUSTOMER_ID, RISK_BAND, STATUS, CREATED_BY, CREATED_AT, REVIEWED_BY FROM CASE_FINDINGS ORDER BY CREATED_AT DESC"),
                     hide_index=True)
    elif st.session_state.audit:
        st.dataframe(pd.DataFrame(st.session_state.audit[::-1]), hide_index=True)
    else:
        st.info("No actions yet. Draft or review a finding in Case investigation and it will be logged here.")
    st.markdown("<span class='sp-muted'>In Snowflake every draft and review is written to AUDIT_LOG with user, role and timestamp. "
                "PAN and account numbers are masked by policy MASK_PII.</span>", unsafe_allow_html=True)

st.markdown("---")
st.markdown("<span class='sp-muted'>Synthetic data only. Policy text is illustrative, not legal advice. "
            "AI-drafted findings require analyst approval (POL-8.3).</span>", unsafe_allow_html=True)
