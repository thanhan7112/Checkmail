import streamlit as st
import requests
import pandas as pd

API_KEYS = ["c985842edb6f4049a6d0977928cdc4a7"]
API_URL = "https://emailvalidation.abstractapi.com/v1/"

def check_email(email, api_key):
    try:
        r = requests.get(API_URL, params={"api_key": api_key, "email": email})
        if r.status_code == 200:
            return r.json()
        return {"error": f"Lỗi API {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}

st.set_page_config(page_title="Công cụ kiểm tra Email", layout="wide")
st.title("📧 Công cụ kiểm tra Email")

emails_input = st.text_area("Nhập danh sách email (mỗi dòng 1 email):")

if st.button("Kiểm tra email"):
    emails = [e.strip() for e in emails_input.splitlines() if e.strip()]
    results = []
    for i, email in enumerate(emails):
        api_key = API_KEYS[i % len(API_KEYS)]
        data = check_email(email, api_key)

        if "error" in data:
            results.append({"Email": email, "Trạng thái": data["error"]})
        else:
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
