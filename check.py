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
    "a2f856614f2d41aca555a01df86b0599",
    "dd2b9a685420437f9933c1bf61889847",
    "2f0d37f98c6345818840dc31c14d2a75",
    "8017751baaea40a7918a299257ef90fb",
    "e6539e72e81c4c948a336a22c40d6565",
    "ee110d38f1d1461f820317426c4fd709",
    "73614f4f15a44082abb40c6d25feb13e"
]
API_URL = "https://emailvalidation.abstractapi.com/v1/"
COMMON_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]

# ========== Abstract API ==========
def check_email_api(email):
    for api_key in API_KEYS:
        try:
            r = requests.get(API_URL, params={"api_key": api_key, "email": email}, timeout=10)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 401:
                continue  # thử key khác
        except Exception:
            continue
    return None  # nếu tất cả key đều lỗi

# ========== Free check ==========
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
    if not re.match(regex, email):
        return result  # định dạng sai thì khỏi check tiếp
    result["is_valid_format"] = {"value": True, "text": "TRUE"}

    # Domain
    domain = email.split("@")[-1]
    if domain in COMMON_DOMAINS:
        return result  # Gmail/Yahoo… bỏ qua SMTP check, sẽ dùng API sau

    # Check MX record
    try:
        mx_records = dns.resolver.resolve(domain, "MX")
        if mx_records:
            result["is_mx_found"] = {"value": True, "text": "TRUE"}

            # Thử kết nối SMTP
            try:
                mx_record = str(mx_records[0].exchange)
                server = smtplib.SMTP(timeout=10)
                server.connect(mx_record)
                server.helo()
                server.quit()
                result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
                result["deliverability"] = "POSSIBLE"
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
        # Bước 1: Free check trước
        free_data = check_email_free(email)

        # Nếu free check fail hoặc domain phổ biến → gọi API
        need_api = (
            free_data["deliverability"] == "UNKNOWN"
            or not free_data["is_mx_found"]["value"]
            or email.split("@")[-1] in COMMON_DOMAINS
        )

        if need_api:
            data = check_email_api(email)
            if data:
                final = data
            else:
                final = free_data
        else:
            final = free_data

        # Chuẩn hóa hiển thị
        results.append({
            "Email": final["email"],
            "Khả năng gửi": final.get("deliverability", "-"),
            "Điểm tin cậy": final.get("quality_score", "-"),
            "Định dạng hợp lệ": "Có" if final["is_valid_format"]["value"] else "Không",
            "Loại email": (
                "Miễn phí" if final["is_free_email"]["value"] else
                "Tạm thời" if final["is_disposable_email"]["value"] else
                "Chung" if final["is_role_email"]["value"] else
                "Bình thường"
            ),
            "Nhận tất cả": "Có" if final["is_catchall_email"]["value"] else "Không",
            "Có MX record": "Có" if final["is_mx_found"]["value"] else "Không",
            "SMTP hợp lệ": "Có" if final["is_smtp_valid"]["value"] else "Không",
        })

    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True)
