"""
Generate synthetic data for StudyPass.

All data is fictional. Names, PANs, and accounts are random tokens.
Fraud patterns are injected deliberately so the risk signals have something to find.

Usage:  python scripts/generate_data.py      -> writes CSVs into ./data
"""
import csv
import os
import random
from datetime import date, datetime, timedelta

random.seed(42)
OUT = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT, exist_ok=True)

FX_INR_PER_USD = 84.0
FY_START = date(2026, 4, 1)

FIRST = ["Aarav", "Vivaan", "Aditya", "Ishaan", "Reyansh", "Ananya", "Diya", "Saanvi", "Myra", "Aadhya",
         "Kabir", "Arjun", "Rohan", "Meera", "Priya", "Karan", "Neha", "Rahul", "Simran", "Tanvi"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Mehta", "Iyer", "Nair", "Reddy", "Kapoor", "Joshi",
        "Malhotra", "Bansal", "Chopra", "Patel", "Das"]
CITIES = ["Delhi", "Mumbai", "Chandigarh", "Pune", "Bengaluru", "Hyderabad", "Jaipur", "Lucknow", "Kochi", "Ahmedabad"]

UNIVERSITIES = [
    ("UNI001", "Technical University of Munich", "DE", 3500),
    ("UNI002", "RWTH Aachen University", "DE", 3000),
    ("UNI003", "University of Toronto", "CA", 45000),
    ("UNI004", "University of Melbourne", "AU", 42000),
    ("UNI005", "University of Manchester", "GB", 33000),
    ("UNI006", "Arizona State University", "US", 32000),
    ("UNI007", "Northeastern University", "US", 58000),
    ("UNI008", "National University of Singapore", "SG", 30000),
    ("UNI009", "University College Dublin", "IE", 26000),
    ("UNI010", "Telkom University", "ID", 4000),
]
HIGH_RISK_COUNTRIES = ["AE", "HK", "CY", "PA"]

MCC_NORMAL = [("5411", "Grocery"), ("5812", "Restaurants"), ("4111", "Local transport"),
              ("5942", "Book stores"), ("8220", "Colleges & universities"), ("4814", "Telecom"),
              ("5311", "Department stores"), ("6513", "Rent / housing")]
MCC_RISKY = [("7995", "Gambling / betting"), ("6051", "Crypto / quasi-cash"), ("4829", "Money transfer")]


def rand_pan():
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(random.choices(L, k=5)) + "".join(random.choices("0123456789", k=4)) + random.choice(L)


def rand_date(start, end):
    return start + timedelta(days=random.randint(0, (end - start).days))


customers, students, remittances, card_txns, documents = [], [], [], [], []
N = 400
pattern_of = {}
patterns = (["STRUCTURING"] * 8 + ["LRS_BREACH"] * 5 + ["THIRD_PARTY"] * 8 + ["COUNTRY_MISMATCH"] * 6 +
            ["INACTIVE_ENROLMENT"] * 6 + ["CARD_RISKY_MCC"] * 7 + ["FEE_INFLATION"] * 6)
flagged_ids = random.sample(range(1, N + 1), len(patterns))
for cid, p in zip(flagged_ids, patterns):
    pattern_of[cid] = p

rem_id = 0
txn_id = 0
doc_id = 0
for i in range(1, N + 1):
    cid = f"C{i:04d}"
    sid = f"S{i:04d}"
    last = random.choice(LAST)
    pf, sf = random.sample(FIRST, 2)
    parent, student = f"{pf} {last}", f"{sf} {last}"
    uni = random.choice(UNIVERSITIES)
    p = pattern_of.get(i)
    enrol = "ACTIVE"
    if p == "INACTIVE_ENROLMENT":
        enrol = random.choice(["WITHDRAWN", "NOT_VERIFIED"])
    intake = rand_date(date(2025, 8, 1), date(2026, 9, 15))
    customers.append({
        "CUSTOMER_ID": cid, "CUSTOMER_NAME": parent, "PAN": rand_pan(), "CITY": random.choice(CITIES),
        "SEGMENT": random.choice(["RETAIL", "RETAIL", "PRIORITY"]),
        "KYC_RISK_RATING": random.choice(["LOW", "LOW", "LOW", "MEDIUM"]) if not p else random.choice(["LOW", "MEDIUM"]),
        "ACCOUNT_NO": "XXXX" + "".join(random.choices("0123456789", k=8)),
        "ONBOARDED_ON": rand_date(date(2015, 1, 1), date(2025, 6, 1)).isoformat(),
    })
    students.append({
        "STUDENT_ID": sid, "CUSTOMER_ID": cid, "STUDENT_NAME": student, "UNIVERSITY_ID": uni[0],
        "UNIVERSITY_NAME": uni[1], "STUDY_COUNTRY": uni[2], "PROGRAM": random.choice(["MSc AI", "MS CS", "MBA", "BEng", "MSc Data Science"]),
        "DECLARED_ANNUAL_FEE_USD": uni[3], "INTAKE_DATE": intake.isoformat(), "ENROLMENT_STATUS": enrol,
        "FOREX_CARD_ID": f"FX{i:05d}",
    })
    # documents (offer letter, fee invoice, Form A2)
    for dtype in ["OFFER_LETTER", "FEE_INVOICE", "FORM_A2"]:
        doc_id += 1
        verified = True
        if p == "INACTIVE_ENROLMENT" and dtype == "OFFER_LETTER":
            verified = False
        documents.append({"DOC_ID": f"D{doc_id:05d}", "CUSTOMER_ID": cid, "STUDENT_ID": sid, "DOC_TYPE": dtype,
                          "VERIFIED": verified, "AMOUNT_USD": uni[3] if dtype == "FEE_INVOICE" else "",
                          "UPLOADED_ON": (intake - timedelta(days=random.randint(20, 90))).isoformat()})

    def add_rem(d, usd, ben_type="UNIVERSITY", country=uni[2], purpose="S0305", ben_name=uni[1]):
        global rem_id
        rem_id += 1
        inr = round(usd * FX_INR_PER_USD)
        remittances.append({
            "REMITTANCE_ID": f"R{rem_id:06d}", "CUSTOMER_ID": cid, "STUDENT_ID": sid, "TXN_DATE": d.isoformat(),
            "AMOUNT_USD": round(usd, 2), "AMOUNT_INR": inr, "PURPOSE_CODE": purpose,
            "BENEFICIARY_TYPE": ben_type, "BENEFICIARY_NAME": ben_name, "BENEFICIARY_COUNTRY": country,
            "CHANNEL": random.choice(["BRANCH", "NETBANKING", "MOBILE"]),
            "TCS_COLLECTED_INR": round(max(0, inr - 1_000_000) * 0.05) if purpose == "S0305" else 0,
        })

    # normal behaviour: tuition + 1-3 living-expense top-ups in FY 2026-27
    fee = uni[3]
    add_rem(rand_date(FY_START, date(2026, 9, 30)), fee * random.uniform(0.5, 1.0))
    for _ in range(random.randint(1, 3)):
        add_rem(rand_date(FY_START, date(2026, 9, 30)), random.uniform(800, 4000), "STUDENT_ACCOUNT", uni[2], "S0305", student)

    # injected patterns
    if p == "STRUCTURING":
        base = rand_date(date(2026, 6, 1), date(2026, 8, 31))
        for k in range(random.randint(4, 6)):
            add_rem(base + timedelta(days=random.randint(0, 25)), random.uniform(11400, 11880), "STUDENT_ACCOUNT", uni[2], "S0305", student)
    elif p == "LRS_BREACH":
        for k in range(3):
            add_rem(rand_date(FY_START, date(2026, 9, 30)), random.uniform(85000, 98000))
    elif p == "THIRD_PARTY":
        for k in range(random.randint(1, 3)):
            add_rem(rand_date(FY_START, date(2026, 9, 30)), random.uniform(6000, 20000), "THIRD_PARTY",
                    random.choice([uni[2]] + HIGH_RISK_COUNTRIES), "S0305",
                    random.choice(["Global Edu Consultants FZE", "Apex Trading Ltd", "Bright Future Holdings"]))
    elif p == "COUNTRY_MISMATCH":
        for k in range(random.randint(1, 2)):
            add_rem(rand_date(FY_START, date(2026, 9, 30)), random.uniform(5000, 15000), "STUDENT_ACCOUNT",
                    random.choice(HIGH_RISK_COUNTRIES), "S0305", student)
    elif p == "INACTIVE_ENROLMENT":
        add_rem(rand_date(date(2026, 7, 1), date(2026, 9, 30)), fee * random.uniform(0.6, 1.0))
    elif p == "FEE_INFLATION":
        add_rem(rand_date(FY_START, date(2026, 9, 30)), fee * random.uniform(1.0, 1.6))

    # forex card transactions
    n_txn = random.randint(8, 25)
    for _ in range(n_txn):
        txn_id += 1
        mcc = random.choice(MCC_NORMAL)
        country = uni[2]
        amt = random.uniform(5, 400)
        if p == "CARD_RISKY_MCC" and random.random() < 0.35:
            mcc = random.choice(MCC_RISKY)
            amt = random.uniform(300, 2500)
            country = random.choice([uni[2]] + HIGH_RISK_COUNTRIES)
        ts = datetime.combine(rand_date(date(2026, 6, 1), date(2026, 9, 30)), datetime.min.time()) + timedelta(minutes=random.randint(0, 1439))
        card_txns.append({"TXN_ID": f"T{txn_id:07d}", "FOREX_CARD_ID": f"FX{i:05d}", "CUSTOMER_ID": cid, "TXN_TS": ts.isoformat(sep=" "),
                          "MCC": mcc[0], "MCC_DESC": mcc[1], "MERCHANT_COUNTRY": country, "AMOUNT_USD": round(amt, 2)})


def dump(name, rows):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows")


dump("customers.csv", customers)
dump("students.csv", students)
dump("remittances.csv", remittances)
dump("card_txns.csv", card_txns)
dump("documents.csv", documents)
dump("ground_truth.csv", [{"CUSTOMER_ID": f"C{k:04d}", "INJECTED_PATTERN": v} for k, v in sorted(pattern_of.items())])
