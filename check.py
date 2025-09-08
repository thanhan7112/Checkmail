import streamlit as st
import requests
import pandas as pd

API_KEYS = [
    "c985842edb6f4049a6d0977928cdc4a7",
]

API_URL = "https://emailvalidation.abstractapi.com/v1/"

def check_email(email, api_key):
    try:
        response = requests.get(API_URL, params={"api_key": api_key, "email": email})
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Lỗi API ({response.status_code})"}
    except Exception as e:
        return {"error": str(e)}

st.title("🔎 Công cụ kiểm tra Email")

emails_input = st.text_area("Nhập danh sách email (mỗi dòng 1 email):")

if st.button("Kiểm tra email"):
    emails = [e.strip() for e in emails_input.splitlines() if e.strip()]
    results = []

    for i, email in enumerate(emails):
        api_key = API_KEYS[i % len(API_KEYS)]  # xoay vòng API key
        data = check_email(email, api_key)

        if "error" in data:
            results.append({
                "Email": email,
                "Trạng thái": data["error"],
            })
        else:
            results.append({
                "Email": data["email"],
                "Gợi ý sửa lỗi": data.get("autocorrect", "-"),
                "Khả năng gửi": data.get("deliverability", "-"),
                "Điểm tin cậy": data.get("quality_score", "-"),
                "Định dạng hợp lệ": "Có" if data["is_valid_format"]["value"] else "Không",
                "Email miễn phí": "Có" if data["is_free_email"]["value"] else "Không",
                "Email tạm thời": "Có" if data["is_disposable_email"]["value"] else "Không",
                "Email nhóm (role)": "Có" if data["is_role_email"]["value"] else "Không",
                "Nhận tất cả (catch-all)": "Có" if data["is_catchall_email"]["value"] else "Không",
                "Có MX record": "Có" if data["is_mx_found"]["value"] else "Không",
                "SMTP hợp lệ": "Có" if data["is_smtp_valid"]["value"] else "Không",
            })

    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True)
