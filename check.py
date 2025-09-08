import streamlit as st
import requests
import pandas as pd
import re
import smtplib
import socket
import dns.resolver
import random
import string
from io import BytesIO

# ========== Cấu hình ==========
API_KEYS = [
    "c985842edb6f4049a6d0977928cdc4a7",
    "0d1f2b3d9f054a2e9fdd398ae019a76b",
    "2b88713468ba46bdb602c007da9d12cc",
    "a2f856614f2d41aca555a01df86b0599",
    "dd2b9a685420437f9933c1bf61889847",
    "2f0d37f98c6345818840dc31c14d2a75",
    "8017751baaea40a7918a299257ef90fb",
    "e6539e72e81c4c948a336a22c40d6565",
    "ee110d38f1d1461f820317426c4fd709",
    "73614f4f15a44082abb40c6d25feb13e",
    "a58021e0795b45e7bd3604f766d01809",
    "14d136c854034f6f95edb27d5264833d",
    "476bcc6eafa84f71abf10152e53c7e1f",
    "aee1766f20ee403ca90dc5dac23153e0",
    "8c81f01b09324dbf9966884b26759bb1"
]
ZERUH_KEYS = [
    "f1cddeb3a52bec71e0aed199845db18ad1ce8630c80a6fdc4b6bb8a19609a929",
]

ABSTRACT_URL = "https://emailvalidation.abstractapi.com/v1/"
ZERUH_URL = "https://api.zeruh.com/v1/verify"

FREE_DOMAINS = {"gmail.com","yahoo.com","outlook.com","hotmail.com","aol.com",
    "icloud.com","mail.com","yandex.com","protonmail.com"}
DISPOSABLE_DOMAINS = {"10minutemail.com","temp-mail.org","mailinator.com","yopmail.com","guerrillamail.com"}
ROLE_ACCOUNTS = {"admin","support","info","contact","sales","hr","billing",
    "postmaster","abuse","noreply","marketing"}

# ======================================================================
# ======================= HÀM KIỂM TRA EMAIL ===========================
# ======================================================================

# 1. Gọi Zeruh API
def check_email_zeruh(email):
    for key in ZERUH_KEYS:
        try:
            r = requests.get(ZERUH_URL, params={"api_key": key, "email_address": email}, timeout=10)
            if r.status_code == 200 and r.json().get("success"):
                data = r.json()["result"]
                return {
                    "email": data.get("email_address"),
                    "deliverability": data.get("status"),
                    "quality_score": data.get("score"),
                    "is_valid_format": {"value": data["validation_details"]["format_valid"], "text": str(data["validation_details"]["format_valid"]).upper()},
                    "is_free_email": {"value": data["validation_details"]["free"], "text": str(data["validation_details"]["free"]).upper()},
                    "is_disposable_email": {"value": data["validation_details"]["disposable"], "text": str(data["validation_details"]["disposable"]).upper()},
                    "is_role_email": {"value": data["validation_details"]["role"], "text": str(data["validation_details"]["role"]).upper()},
                    "is_catchall_email": {"value": data["validation_details"]["catch_all"], "text": str(data["validation_details"]["catch_all"]).upper()},
                    "is_mx_found": {"value": data["validation_details"]["mx_found"], "text": str(data["validation_details"]["mx_found"]).upper()},
                    "is_smtp_valid": {"value": data["validation_details"]["smtp_check"], "text": str(data["validation_details"]["smtp_check"]).upper()},
                }
        except:
            continue
    return None

# 2. Gọi AbstractAPI
def check_email_abstract(email):
    for key in ABSTRACT_KEYS:
        try:
            r = requests.get(ABSTRACT_URL, params={"api_key": key, "email": email}, timeout=10)
            if r.status_code == 200:
                return r.json()
        except:
            continue
    return None

# 3. Lấy MX record
def get_mx_records_robust(domain):
    try:
        records = dns.resolver.resolve(domain, 'MX')
        mx_records = sorted([(r.preference, r.exchange.to_text()) for r in records])
        return mx_records
    except:
        try:
            r = requests.get(f"https://dns.google/resolve?name={domain}&type=MX", timeout=5)
            r.raise_for_status()
            data = r.json()
            if "Answer" in data:
                answers = sorted(
                    [ans["data"].split() for ans in data.get("Answer", []) if ans.get("type") == 15],
                    key=lambda x: int(x[0])
                )
                return [(int(p), ex) for p, ex in answers]
            return []
        except:
            return []

# 4. Kiểm tra miễn phí nâng cao
def check_email_free_super_advanced(email):
    result = {
        "email": email, "deliverability": "UNKNOWN", "quality_score": "-",
        "is_valid_format": {"value": False, "text": "FALSE"},
        "is_free_email": {"value": False, "text": "FALSE"},
        "is_disposable_email": {"value": False, "text": "FALSE"},
        "is_role_email": {"value": False, "text": "FALSE"},
        "is_catchall_email": {"value": False, "text": "UNKNOWN"},
        "is_mx_found": {"value": False, "text": "FALSE"},
        "is_smtp_valid": {"value": False, "text": "UNKNOWN"},
    }

    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_valid_format"] = {"value": True, "text": "TRUE"}

    local_part, domain = email.split("@")

    if domain in FREE_DOMAINS:
        result["is_free_email"] = {"value": True, "text": "TRUE"}
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable_email"] = {"value": True, "text": "TRUE"}
        result["deliverability"] = "UNDELIVERABLE"
        return result
    if local_part.lower() in ROLE_ACCOUNTS:
        result["is_role_email"] = {"value": True, "text": "TRUE"}

    mx_records = get_mx_records_robust(domain)
    if not mx_records:
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_mx_found"] = {"value": True, "text": "TRUE"}

    if result["is_free_email"]["value"]:
        result["deliverability"] = "DELIVERABLE"
        result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
        return result

    for _, mx_record in mx_records:
        try:
            with smtplib.SMTP(mx_record, 25, timeout=10) as server:
                hostname = socket.getfqdn() or 'example.com'
                server.ehlo(hostname)
                server.mail(f'verify@{hostname}')
                code, _ = server.rcpt(str(email))

                if code == 250:
                    result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
                    result["deliverability"] = "DELIVERABLE"

                    random_local = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(20))
                    random_email = f"{random_local}@{domain}"
                    code_catchall, _ = server.rcpt(random_email)

                    if code_catchall == 250:
                        result["is_catchall_email"] = {"value": True, "text": "TRUE"}
                        result["deliverability"] = "RISKY"
                    else:
                        result["is_catchall_email"] = {"value": False, "text": "FALSE"}
                    return result

                elif code >= 500:
                    result["is_smtp_valid"] = {"value": False, "text": "FALSE"}
                    result["deliverability"] = "UNDELIVERABLE"
                    return result
        except:
            continue
    return result

# ======================================================================
# ========================== GIAO DIỆN UI ==============================
# ======================================================================

st.set_page_config(page_title="Công cụ kiểm tra Email", layout="wide", initial_sidebar_state="collapsed")
st.title("📧 Công cụ kiểm tra Email (Có Zeruh + AbstractAPI)")

emails_input = st.text_area(
    "Nhập danh sách email (mỗi email một dòng):",
    height=250,
    placeholder="example@gmail.com\nsupport@company.com\nwrong-email@domain",
)

if st.button("🚀 Bắt đầu kiểm tra", use_container_width=True):
    emails = [e.strip().lower() for e in emails_input.splitlines() if e.strip()]
    
    if not emails:
        st.warning("Vui lòng nhập ít nhất một email để kiểm tra.")
    else:
        results = []
        progress_bar = st.progress(0, text="Bắt đầu...")
        status_text = st.empty()

        for i, email in enumerate(emails):
            status_text.text(f"⚙️ Đang kiểm tra: {email} ({i+1}/{len(emails)})")

            final_data = check_email_free_super_advanced(email)
            is_risky = final_data["deliverability"] in ["UNKNOWN", "RISKY"]
            is_free = final_data["is_free_email"]["value"]

            if is_risky or is_free:
                api_data = check_email_zeruh(email)
                if not api_data:
                    api_data = check_email_abstract(email)
                if api_data:
                    final_data = api_data

            results.append({
                "Email": final_data.get("email"),
                "Khả năng gửi": final_data.get("deliverability", "-"),
                "Điểm tin cậy": final_data.get("quality_score", "-"),
                "Định dạng hợp lệ": "✅ Có" if final_data.get("is_valid_format", {}).get("value") else "❌ Không",
                "Loại email": (
                    "Miễn phí" if final_data.get("is_free_email", {}).get("value") else
                    "Tạm thời" if final_data.get("is_disposable_email", {}).get("value") else
                    "Chung" if final_data.get("is_role_email", {}).get("value") else
                    "Bình thường"
                ),
                "Nhận tất cả (Catchall)": "✅ Có" if final_data.get("is_catchall_email", {}).get("value") else "❌ Không",
                "Có MX record": "✅ Có" if final_data.get("is_mx_found", {}).get("value") else "❌ Không",
                "SMTP hợp lệ": "✅ Có" if final_data.get("is_smtp_valid", {}).get("value") else "❌ Không",
            })

            progress_bar.progress((i + 1) / len(emails), text=f"Hoàn thành {i+1}/{len(emails)}")

        status_text.success("🎉 Hoàn thành kiểm tra!")
        df = pd.DataFrame(results)

        st.subheader("Bảng kết quả")
        st.dataframe(df, use_container_width=True)

        st.subheader("Tải về kết quả")
        col1, col2 = st.columns(2)

        csv = df.to_csv(index=False).encode("utf-8")
        with col1:
            st.download_button("📥 Tải về file CSV", data=csv,
                               file_name="ket_qua_kiem_tra_email.csv",
                               mime="text/csv", use_container_width=True)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Kết quả")
        with col2:
            st.download_button("📥 Tải về file Excel", data=output.getvalue(),
                               file_name="ket_qua_kiem_tra_email.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)