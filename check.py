import streamlit as st
import requests
import pandas as pd
import re
import dns.resolver
import smtplib

# ========== Cấu hình ==========
API_KEYS = [
    "c985842edb6f4049a6d0977928cdc4a7",
    "0d1f2b3d9f054a2e9fdd398ae019a76b",
    "2b88713468ba46bdb602c007da9d12cc",
    "a2f856614f2d41aca555a01df86b0599"
]
API_URL = "https://emailvalidation.abstractapi.com/v1/"

# ========== Abstract API ==========
def check_email_api(email):
    for api_key in API_KEYS:
        try:
            r = requests.get(API_URL, params={"api_key": api_key, "email": email})
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 401:
                continue  # thử key khác
        except Exception:
            continue
    return None  # nếu tất cả key đều lỗi

# ========== Fallback: kiểm tra miễn phí ==========
def check_email_free(email):
    result = {
        "email": email,
        "deliverability": "UNKNOWN",
        "quality_score": "-",
        "is_valid_format": {"value": False, "text": "FALSE"},
        "is_free_email": {"value": False, "text": "FALSE"},
        "is_disposable_email": {"value": False, "text": "FALSE"},
        "is_role_email": {"value": False, "text": "FALSE"},
        "is_catchall_email": {"value": False, "text": "FALSE"},
        "is_mx_found": {"value": False, "text": "FALSE"},
        "is_smtp_valid": {"value": False, "text": "FALSE"},
    }

    # Regex check format
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if re.match(regex, email):
        result["is_valid_format"] = {"value": True, "text": "TRUE"}

    # Check MX record
    domain = email.split("@")[-1]
    try:
        mx_records = dns.resolver.resolve(domain, "MX")
        if mx_records:
            result["is_mx_found"] = {"value": True, "text": "TRUE"}

            # Thử kết nối SMTP (chỉ kiểm tra được server, không luôn luôn chính xác)
            try:
                mx_record = str(mx_records[0].exchange)
                server = smtplib.SMTP(timeout=10)
                server.connect(mx_record)
                server.helo()
                server.quit()
                result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
            except Exception:
                pass
    except Exception:
        pass

    return result

# ========== Streamlit App ==========
st.set_page_config(page_title="Công cụ kiểm tra Email", layout="wide")
st.title("📧 Công cụ kiểm tra Email (Nguyen Thanh An)")

emails_input = st.text_area("Nhập danh sách email (mỗi dòng 1 email):")

if st.button("Kiểm tra email"):
    emails = [e.strip() for e in emails_input.splitlines() if e.strip()]
    results = []
    for email in emails:
        data = check_email_api(email)
        if not data:  # fallback sang free check
            data = check_email_free(email)

        # Chuẩn hóa hiển thị
        results.append({
            "Email": data["email"],
            "Khả năng gửi": data.get("deliverability", "-"),
            "Điểm tin cậy": data.get("quality_score", "-"),
            "Định dạng hợp lệ": "Có" if data["is_valid_format"]["value"] else "Không",
            "Loại email": (
                "Miễn phí" if data["is_free_email"]["value"] else
                "Tạm thời" if data["is_disposable_email"]["value"] else
                "Chung" if data["is_role_email"]["value"] else
                "Bình thường"
            ),
            "Nhận tất cả": "Có" if data["is_catchall_email"]["value"] else "Không",
            "Có MX record": "Có" if data["is_mx_found"]["value"] else "Không",
            "SMTP hợp lệ": "Có" if data["is_smtp_valid"]["value"] else "Không",
        })

    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True)
