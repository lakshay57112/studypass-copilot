"""
StudyPass risk engine (local / demo mode).

Mirrors sql/04_risk_signals.sql and sql/05_findings.sql in pandas so the public demo
runs without a Snowflake connection. In Snowflake mode the app reads the views instead.
"""
import os
import re
from datetime import date

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
HIGH_RISK = {"AE", "HK", "CY", "PA"}
RISKY_MCC = {"7995", "6051", "4829"}
WEIGHTS = {"LRS_BREACH": 40, "STRUCTURING": 30, "THIRD_PARTY_BENEFICIARY": 30, "INACTIVE_ENROLMENT": 25,
           "COUNTRY_MISMATCH": 20, "CARD_RISKY_MCC": 20, "FEE_INFLATION": 15}
CLAUSE = {"LRS_BREACH": "POL-2.1", "STRUCTURING": "POL-5.2", "THIRD_PARTY_BENEFICIARY": "POL-3.2",
          "INACTIVE_ENROLMENT": "POL-4.2", "COUNTRY_MISMATCH": "POL-3.3", "CARD_RISKY_MCC": "POL-6.2",
          "FEE_INFLATION": "POL-4.3"}
SIGNAL_LABEL = {"LRS_BREACH": "LRS limit breach", "STRUCTURING": "Structuring below INR 10 lakh",
                "THIRD_PARTY_BENEFICIARY": "Third-party beneficiary", "INACTIVE_ENROLMENT": "Inactive / unverified enrolment",
                "COUNTRY_MISMATCH": "Destination country mismatch", "CARD_RISKY_MCC": "Risky forex-card spend",
                "FEE_INFLATION": "Tuition above declared fee"}


def fy_start(d):
    return date(d.year if d.month >= 4 else d.year - 1, 4, 1)


def load_data(data_dir=None):
    d = data_dir or os.path.join(ROOT, "data")
    dfs = {n: pd.read_csv(os.path.join(d, f"{n}.csv"), dtype=str) for n in
           ["customers", "students", "remittances", "card_txns", "documents"]}
    r = dfs["remittances"]
    r["TXN_DATE"] = pd.to_datetime(r["TXN_DATE"]).dt.date
    for c in ["AMOUNT_USD", "AMOUNT_INR", "TCS_COLLECTED_INR"]:
        r[c] = pd.to_numeric(r[c])
    c = dfs["card_txns"]
    c["AMOUNT_USD"] = pd.to_numeric(c["AMOUNT_USD"])
    c["TXN_TS"] = pd.to_datetime(c["TXN_TS"])
    s = dfs["students"]
    s["DECLARED_ANNUAL_FEE_USD"] = pd.to_numeric(s["DECLARED_ANNUAL_FEE_USD"])
    dfs["documents"]["VERIFIED"] = dfs["documents"]["VERIFIED"].str.lower().eq("true")
    return dfs


def load_policy():
    rows = []
    path = os.path.join(ROOT, "policies", "education_remittance_policy.md")
    section = ""
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("## "):
            section = line[3:]
        m = re.match(r"^(POL-\d+\.\d+)\s+(.*)$", line)
        if m:
            rows.append({"CLAUSE_ID": m.group(1), "SECTION": section, "CLAUSE_TEXT": m.group(2)})
    return pd.DataFrame(rows)


def _sig(cid, code, metric, evidence, detail):
    return {"CUSTOMER_ID": cid, "SIGNAL_CODE": code, "WEIGHT": WEIGHTS[code], "METRIC_VALUE": round(float(metric), 2),
            "EVIDENCE_IDS": list(evidence), "POLICY_CLAUSE": CLAUSE[code], "DETAIL": detail}


def compute_signals(dfs):
    r, s, c, d = dfs["remittances"].copy(), dfs["students"], dfs["card_txns"], dfs["documents"]
    r["FY"] = r["TXN_DATE"].map(fy_start)
    edu = r[r["PURPOSE_CODE"] == "S0305"].merge(s[["STUDENT_ID", "STUDY_COUNTRY", "DECLARED_ANNUAL_FEE_USD",
                                                   "ENROLMENT_STATUS", "UNIVERSITY_NAME"]], on="STUDENT_ID")
    out = []

    for (cid, fy), g in r.groupby(["CUSTOMER_ID", "FY"]):
        tot = g["AMOUNT_USD"].sum()
        if tot > 250000:
            out.append(_sig(cid, "LRS_BREACH", tot, g.sort_values("TXN_DATE")["REMITTANCE_ID"],
                            f"FY {fy.year} LRS total USD {tot:,.0f} exceeds USD 250,000 limit"))

    band = edu[(edu["AMOUNT_INR"] >= 900000) & (edu["AMOUNT_INR"] < 1000000)]
    for cid, g in band.groupby("CUSTOMER_ID"):
        dates = sorted(g["TXN_DATE"])
        mx = max(sum(1 for b in dates if 0 <= (b - a).days <= 30) for a in dates)
        if mx >= 3:
            out.append(_sig(cid, "STRUCTURING", len(g), g.sort_values("TXN_DATE")["REMITTANCE_ID"],
                            f"{len(g)} remittances of INR 9-10 lakh each (just below the INR 10 lakh threshold), max {mx} within 30 days"))

    tp = edu[edu["BENEFICIARY_TYPE"] == "THIRD_PARTY"]
    for cid, g in tp.groupby("CUSTOMER_ID"):
        out.append(_sig(cid, "THIRD_PARTY_BENEFICIARY", g["AMOUNT_USD"].sum(), g.sort_values("TXN_DATE")["REMITTANCE_ID"],
                        f"{len(g)} education remittance(s) totalling USD {g['AMOUNT_USD'].sum():,.0f} paid to third party: "
                        + ", ".join(sorted(g["BENEFICIARY_NAME"].unique()))))

    mm = edu[edu["BENEFICIARY_COUNTRY"] != edu["STUDY_COUNTRY"]]
    for cid, g in mm.groupby("CUSTOMER_ID"):
        hr = " (high-risk jurisdiction)" if set(g["BENEFICIARY_COUNTRY"]) & HIGH_RISK else ""
        out.append(_sig(cid, "COUNTRY_MISMATCH", g["AMOUNT_USD"].sum(), g.sort_values("TXN_DATE")["REMITTANCE_ID"],
                        f"Student studies in {g['STUDY_COUNTRY'].iloc[0]} but funds sent to "
                        + ", ".join(sorted(g["BENEFICIARY_COUNTRY"].unique())) + hr))

    ina = edu[edu["ENROLMENT_STATUS"] != "ACTIVE"]
    for cid, g in ina.groupby("CUSTOMER_ID"):
        docs = d[(d["STUDENT_ID"].isin(g["STUDENT_ID"])) & (~d["VERIFIED"])]["DOC_ID"]
        out.append(_sig(cid, "INACTIVE_ENROLMENT", g["AMOUNT_USD"].sum(), list(g["REMITTANCE_ID"]) + list(docs),
                        f"Enrolment status {g['ENROLMENT_STATUS'].iloc[0]} at {g['UNIVERSITY_NAME'].iloc[0]}; "
                        f"offer letter not verified; {len(g)} remittance(s) still sent"))

    uni = edu[edu["BENEFICIARY_TYPE"] == "UNIVERSITY"]
    for (cid, fy), g in uni.groupby(["CUSTOMER_ID", "FY"]):
        fee = g["DECLARED_ANNUAL_FEE_USD"].iloc[0]
        tot = g["AMOUNT_USD"].sum()
        if tot > 1.2 * fee:
            out.append(_sig(cid, "FEE_INFLATION", tot / fee, g.sort_values("TXN_DATE")["REMITTANCE_ID"],
                            f"Tuition paid USD {tot:,.0f} = {100 * tot / fee:.0f}% of declared fee (limit 120%)"))

    rc = c[c["MCC"].isin(RISKY_MCC)]
    for cid, g in rc.groupby("CUSTOMER_ID"):
        hr = bool(set(g["MERCHANT_COUNTRY"]) & HIGH_RISK)
        if len(g) >= 2 or hr:
            out.append(_sig(cid, "CARD_RISKY_MCC", g["AMOUNT_USD"].sum(), g.sort_values("TXN_TS")["TXN_ID"],
                            f"{len(g)} forex-card txn(s) at " + ", ".join(sorted(g["MCC_DESC"].unique()))
                            + f" totalling USD {g['AMOUNT_USD'].sum():,.0f}" + (", incl. high-risk jurisdiction" if hr else "")))

    return pd.DataFrame(out)


def customer_risk(signals, customers):
    g = signals.sort_values("WEIGHT", ascending=False).groupby("CUSTOMER_ID").agg(
        RISK_SCORE=("WEIGHT", "sum"), SIGNALS=("SIGNAL_CODE", list), POLICY_CLAUSES=("POLICY_CLAUSE", lambda x: sorted(set(x)))
    ).reset_index()
    g["RISK_BAND"] = pd.cut(g["RISK_SCORE"], [-1, 19, 39, 10_000], labels=["LOW", "MEDIUM", "HIGH"]).astype(str)
    g = g.merge(customers[["CUSTOMER_ID", "CUSTOMER_NAME", "CITY", "KYC_RISK_RATING"]], on="CUSTOMER_ID")
    return g.sort_values(["RISK_SCORE", "CUSTOMER_ID"], ascending=[False, True]).reset_index(drop=True)


def evidence_for(cid, signals, dfs):
    rows = []
    r = dfs["remittances"].set_index("REMITTANCE_ID")
    c = dfs["card_txns"].set_index("TXN_ID")
    d = dfs["documents"].set_index("DOC_ID")
    for _, s in signals[signals["CUSTOMER_ID"] == cid].iterrows():
        for eid in s["EVIDENCE_IDS"]:
            if eid in r.index:
                x = r.loc[eid]
                text = (f"Remittance {eid} on {x.TXN_DATE}: USD {x.AMOUNT_USD:,.2f} (INR {x.AMOUNT_INR:,.0f}) to {x.BENEFICIARY_NAME} "
                        f"[{x.BENEFICIARY_TYPE}, {x.BENEFICIARY_COUNTRY}], purpose {x.PURPOSE_CODE}")
            elif eid in c.index:
                x = c.loc[eid]
                text = f"Card txn {eid} at {x.TXN_TS}: USD {x.AMOUNT_USD:,.2f}, MCC {x.MCC} {x.MCC_DESC} in {x.MERCHANT_COUNTRY}"
            elif eid in d.index:
                x = d.loc[eid]
                text = f"Document {eid}: {x.DOC_TYPE}, verified={x.VERIFIED}, uploaded {x.UPLOADED_ON}"
            else:
                text = eid
            rows.append({"SIGNAL_CODE": s["SIGNAL_CODE"], "POLICY_CLAUSE": s["POLICY_CLAUSE"], "EVIDENCE_ID": eid, "EVIDENCE_TEXT": text})
    return pd.DataFrame(rows)


def draft_finding(cid, signals, risk, dfs, policy):
    """Template narrative used in demo mode. In Snowflake, SP_DRAFT_FINDING writes this with Cortex COMPLETE."""
    rk = risk[risk["CUSTOMER_ID"] == cid].iloc[0]
    cust = dfs["customers"].set_index("CUSTOMER_ID").loc[cid]
    stu = dfs["students"].set_index("CUSTOMER_ID").loc[cid]
    sig = signals[signals["CUSTOMER_ID"] == cid].sort_values("WEIGHT", ascending=False)
    clauses = sorted(set(sig["POLICY_CLAUSE"]) | {"POL-7.2", "POL-8.1", "POL-8.2", "POL-8.3"})
    pol = policy.set_index("CLAUSE_ID")

    def ids(lst, n=6):
        lst = list(lst)
        more = f" +{len(lst) - n} more" if len(lst) > n else ""
        return ", ".join(f"[{x}]" for x in lst[:n]) + more

    rec = ("File STR with FIU-IND within 7 working days of the analyst confirming suspicion (POL-8.1), "
           "and pause further S0305 remittances pending enhanced due diligence."
           if rk["RISK_BAND"] == "HIGH" else
           "Enhanced due diligence: request a fresh fee invoice / enrolment proof and re-assess within 2 working days (POL-7.2).")
    lines = [
        f"**DRAFT - pending analyst review** · Customer {cid} · Risk score {rk['RISK_SCORE']} ({rk['RISK_BAND']})",
        "",
        "### 1. Summary",
        f"{len(sig)} risk signal(s) fired on education remittances and forex-card activity linked to {cust.CUSTOMER_NAME} "
        f"(remitter) for student {stu.STUDENT_NAME}. Combined weight {rk['RISK_SCORE']} puts the case in the {rk['RISK_BAND']} band (POL-7.2).",
        "",
        "### 2. Customer & student profile",
        f"- Remitter: {cust.CUSTOMER_NAME}, {cust.CITY}, segment {cust.SEGMENT}, KYC rating {cust.KYC_RISK_RATING}, PAN ******{cust.PAN[-4:]}",
        f"- Student: {stu.STUDENT_NAME}, {stu.PROGRAM} at {stu.UNIVERSITY_NAME} ({stu.STUDY_COUNTRY}), enrolment {stu.ENROLMENT_STATUS}, "
        f"declared annual fee USD {float(stu.DECLARED_ANNUAL_FEE_USD):,.0f}",
        "",
        "### 3. Red flags",
    ]
    for _, s in sig.iterrows():
        lines.append(f"- **{SIGNAL_LABEL[s['SIGNAL_CODE']]}** ({s['POLICY_CLAUSE']}): {s['DETAIL']}. Evidence: {ids(s['EVIDENCE_IDS'])}")
    lines += ["", "### 4. Policy assessment"]
    for cl in clauses:
        if cl in pol.index:
            lines.append(f"- ({cl}) {pol.loc[cl, 'CLAUSE_TEXT']}")
    lines += ["", "### 5. Recommendation", rec,
              "Do not disclose the review to the customer (POL-8.2).",
              "", "### 6. Open questions for the reviewer",
              "- Is there a university authorisation or explanation on file that clears any of the flags above?",
              "- Are there remittances for this PAN through other banks this financial year (LRS is across all banks)?"]
    return "\n".join(lines)


_STOP = {"the", "and", "what", "when", "which", "who", "how", "can", "does", "for", "are", "with", "that", "this",
         "from", "into", "our", "any", "should", "must", "will", "about", "there", "their", "they", "has", "have",
         "been", "was", "were", "you", "your", "its", "not", "but", "all", "per", "than", "then", "also", "out", "fast",
         "happens", "happen"}
_SYN = {"agent": ["third", "party"], "agents": ["third", "party"], "consultant": ["third", "party"],
        "limit": ["lrs", "250"], "breach": ["exceed", "above"], "split": ["structuring"], "structuring": ["threshold"],
        "gambling": ["7995"], "crypto": ["6051"], "str": ["suspicious"], "filed": ["file", "days"],
        "deadline": ["days"], "fee": ["invoice", "tuition"], "customers": ["customer"], "remittances": ["remittance"]}


def _terms(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP]


def search_policy(question, policy, k=4):
    """Keyword retrieval used in demo mode. In Snowflake, the compliance-qa skill uses Cortex Search (POLICY_SEARCH).

    Whole-word matching, stopwords removed, rarer terms weighted higher (IDF), section titles count double."""
    import math
    q = set(_terms(question))
    expanded = {s for w in q for s in _SYN.get(w, [])} - q
    docs = [set(_terms(t)) for t in policy["CLAUSE_TEXT"]]
    secs = [set(_terms(t)) for t in policy["SECTION"]]
    n = len(docs) or 1
    df = {w: sum(w in d or w in s for d, s in zip(docs, secs)) for w in q | expanded}
    idf = {w: math.log((n + 1) / (c + 0.5)) for w, c in df.items()}

    def score(d, s):
        tot = 0.0
        for w in q | expanded:
            wt = idf[w] * (1.0 if w in q else 0.6)
            tot += wt * ((w in d) + 2 * (w in s))
        return round(tot, 3)

    scored = policy.assign(SCORE=[score(d, s) for d, s in zip(docs, secs)])
    return scored[scored["SCORE"] > 0].sort_values("SCORE", ascending=False, kind="stable").head(k)
