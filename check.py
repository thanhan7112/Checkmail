import streamlit as st
import requests
import pandas as pd
import re
import dns.resolver
import smtplib
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
    "e6539e72e81c4c948a336a22c40d6565"
]
API_URL = "https://emailvalidation.abstractapi.com/v1/"

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
    return None

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

    # Regex check
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if re.match(regex, email):
        result["is_valid_format"] = {"value": True, "text": "TRUE"}

    # MX record
    domain = email.split("@")[-1]
    try:
        mx_records = dns.resolver.resolve(domain, "MX")
        if mx_records:
            result["is_mx_found"] = {"value": True, "text": "TRUE"}

            # SMTP handshake
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

# ========== App ==========
st.set_page_config(page_title="Công cụ kiểm tra Email", layout="wide")
st.title("📧 Công cụ kiểm tra Email (Nguyen Thanh An)")

emails_input = st.text_area("Nhập danh sách email (mỗi dòng 1 email):")

if st.button("Kiểm tra email"):
    emails = [e.strip() for e in emails_input.splitlines() if e.strip()]
    results = []

    with st.spinner("⏳ Đang kiểm tra..."):
        for email in emails:
            data = check_email_free(email)

            # fallback sang AbstractAPI nếu không chắc chắn
            if (data["deliverability"] == "UNKNOWN" or
                not data["is_valid_format"]["value"] or
                not data["is_mx_found"]["value"] or
                not data["is_smtp_valid"]["value"]):
                api_data = check_email_api(email)
                if api_data:
                    data = api_data

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

    # Xuất CSV
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Tải về CSV",
        data=csv,
        file_name="emails_checked.csv",
        mime="text/csv",
    )

    # Xuất Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Emails")
    st.download_button(
        label="📥 Tải về Excel",
        data=output.getvalue(),
        file_name="emails_checked.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
