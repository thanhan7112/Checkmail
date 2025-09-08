import streamlit as st
import requests
import pandas as pd
import re
import smtplib
import socket
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
API_URL = "https://emailvalidation.abstractapi.com/v1/"

FREE_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com",
    "icloud.com", "mail.com", "yandex.com", "protonmail.com"
}
DISPOSABLE_DOMAINS = {
    "10minutemail.com", "temp-mail.org", "mailinator.com", "yopmail.com",
    "guerrillamail.com"
}
ROLE_ACCOUNTS = {
    "admin", "support", "info", "contact", "sales", "hr", "billing",
    "postmaster", "abuse", "noreply", "marketing"
}

# ========== Abstract API ==========
def check_email_api(email):
    for api_key in API_KEYS:
        try:
            r = requests.get(API_URL, params={"api_key": api_key, "email": email}, timeout=10)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 401:
                continue  # thử key khác
        except requests.exceptions.RequestException:
            continue
    return None

# ========== Lấy MX record qua Google DNS ==========
def get_mx_records(domain):
    try:
        r = requests.get(
            f"https://dns.google/resolve?name={domain}&type=MX",
            timeout=5
        )
        data = r.json()
        if "Answer" in data:
            return [ans["data"] for ans in data["Answer"] if ans["type"] == 15]
        return []
    except:
        return []

# ========== Free Check nâng cấp ==========
def check_email_free_advanced(email):
    result = {
        "email": email, "deliverability": "UNKNOWN", "quality_score": "-",
        "is_valid_format": {"value": False, "text": "FALSE"},
        "is_free_email": {"value": False, "text": "FALSE"},
        "is_disposable_email": {"value": False, "text": "FALSE"},
        "is_role_email": {"value": False, "text": "FALSE"},
        "is_catchall_email": {"value": False, "text": "UNKNOWN"},
        "is_mx_found": {"value": False, "text": "FALSE"},
        "is_smtp_valid": {"value": False, "text": "FALSE"},
    }

    # 1. Regex format
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_valid_format"] = {"value": True, "text": "TRUE"}

    local_part, domain = email.split("@")

    # 2. Kiểm tra loại email
    if domain in FREE_DOMAINS:
        result["is_free_email"] = {"value": True, "text": "TRUE"}
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable_email"] = {"value": True, "text": "TRUE"}
        result["deliverability"] = "UNDELIVERABLE"
        return result
    if local_part.lower() in ROLE_ACCOUNTS:
        result["is_role_email"] = {"value": True, "text": "TRUE"}

    # 3. MX lookup
    mx_records = get_mx_records(domain)
    if not mx_records:
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_mx_found"] = {"value": True, "text": "TRUE"}
    mx_record = mx_records[0].split()[-1]

    # 4. SMTP check (bỏ qua email miễn phí vì thường chặn)
    if result["is_free_email"]["value"]:
        return result

    try:
        server = smtplib.SMTP(mx_record, timeout=10)
        server.set_debuglevel(0)
        server.ehlo()
        server.mail('test@example.com')
        code, message = server.rcpt(email)
        server.quit()

        if code == 250:
            result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
            result["deliverability"] = "DELIVERABLE"
        elif code == 550:
            result["is_smtp_valid"] = {"value": False, "text": "FALSE"}
            result["deliverability"] = "UNDELIVERABLE"
        else:
            result["deliverability"] = "RISKY"

    except Exception:
        result["deliverability"] = "UNKNOWN"

    return result

# ========== Streamlit App ==========
st.set_page_config(page_title="Công cụ kiểm tra Email", layout="wide")
st.title("📧 Công cụ kiểm tra Email (Phiên bản nâng cấp)")

emails_input = st.text_area("Nhập danh sách email (mỗi dòng 1 email):", height=200)

if st.button("Kiểm tra email"):
    emails = [e.strip().lower() for e in emails_input.splitlines() if e.strip()]
    results = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, email in enumerate(emails):
        status_text.text(f"Đang kiểm tra: {email} ({i+1}/{len(emails)})")

        free_data = check_email_free_advanced(email)

        need_api = (
            free_data["deliverability"] in ["UNKNOWN", "RISKY"]
            or free_data["is_free_email"]["value"]
        )

        final_data = free_data
        if need_api:
            api_data = check_email_api(email)
            if api_data:
                final_data = api_data

        results.append({
            "Email": final_data.get("email"),
            "Khả năng gửi": final_data.get("deliverability", "-"),
            "Điểm tin cậy": final_data.get("quality_score", "-"),
            "Định dạng hợp lệ": "Có" if final_data.get("is_valid_format", {}).get("value") else "Không",
            "Loại email": (
                "Miễn phí" if final_data.get("is_free_email", {}).get("value") else
                "Tạm thời" if final_data.get("is_disposable_email", {}).get("value") else
                "Chung" if final_data.get("is_role_email", {}).get("value") else
                "Bình thường"
            ),
            "Nhận tất cả (Catchall)": "Có" if final_data.get("is_catchall_email", {}).get("value") else "Không",
            "Có MX record": "Có" if final_data.get("is_mx_found", {}).get("value") else "Không",
            "SMTP hợp lệ": "Có" if final_data.get("is_smtp_valid", {}).get("value") else "Không",
        })

        progress_bar.progress((i + 1) / len(emails))

    status_text.text("Hoàn thành!")
    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True)

    # Download CSV
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Tải về CSV",
        data=csv,
        file_name="email_check_results.csv",
        mime="text/csv"
    )

    # Download Excel (openpyxl)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Kết quả")
    st.download_button(
        label="📥 Tải về Excel",
        data=output.getvalue(),
        file_name="email_check_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
