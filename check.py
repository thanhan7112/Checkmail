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

# ========== Abstract API (Không thay đổi) ==========
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
    return None  # nếu tất cả key đều lỗi

# ========== Free Check NÂNG CẤP ==========
def check_email_free_advanced(email):
    # Khởi tạo kết quả mặc định
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

    # 1. Kiểm tra định dạng (Regex)
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_valid_format"] = {"value": True, "text": "TRUE"}

    # Tách local part và domain
    local_part, domain = email.split("@")

    # 2. Kiểm tra các loại email dựa trên danh sách
    if domain in FREE_DOMAINS:
        result["is_free_email"] = {"value": True, "text": "TRUE"}
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable_email"] = {"value": True, "text": "TRUE"}
        result["deliverability"] = "UNDELIVERABLE" # Email tạm thời coi như không gửi được
        return result
    if local_part.lower() in ROLE_ACCOUNTS:
        result["is_role_email"] = {"value": True, "text": "TRUE"}

    # 3. Kiểm tra bản ghi MX (DNS)
    try:
        mx_records = dns.resolver.resolve(domain, "MX")
        if not mx_records:
            result["deliverability"] = "UNDELIVERABLE"
            return result
        result["is_mx_found"] = {"value": True, "text": "TRUE"}
        mx_record = str(mx_records[0].exchange)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.exception.Timeout):
        result["deliverability"] = "UNDELIVERABLE"
        return result

    # 4. Kiểm tra SMTP sâu (Xác thực người nhận)
    # Các nhà cung cấp lớn (Gmail, Outlook) thường chặn cách này, nên ta bỏ qua.
    if result["is_free_email"]["value"]:
        return result # Trả về kết quả hiện tại và để logic chính gọi API

    try:
        # Kết nối tới server mail
        server = smtplib.SMTP(mx_record, timeout=10)
        server.set_debuglevel(0)
        server.ehlo()
        
        # Gửi lệnh MAIL FROM
        # Một số server yêu cầu địa chỉ email hợp lệ
        server.mail('test@example.com')
        
        # Gửi lệnh RCPT TO để kiểm tra email
        # Đây là bước quan trọng nhất
        code, message = server.rcpt(email)
        server.quit()

        if code == 250: # Mã 250: OK - Địa chỉ email tồn tại
            result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
            result["deliverability"] = "DELIVERABLE"
        elif code == 550: # Mã 550: User unknown - Không tồn tại
            result["is_smtp_valid"] = {"value": False, "text": "FALSE"}
            result["deliverability"] = "UNDELIVERABLE"
        else: # Các mã khác (4xx - lỗi tạm thời) -> không chắc chắn
            result["deliverability"] = "RISKY"

    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, socket.timeout, socket.error):
        # Không thể kết nối hoặc server từ chối, không thể xác định
        result["deliverability"] = "UNKNOWN"
    except Exception:
        result["deliverability"] = "UNKNOWN"

    return result

# ========== Streamlit App (Logic được cập nhật) ==========
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

        # Bước 1: Luôn chạy Free check nâng cấp trước
        free_data = check_email_free_advanced(email)

        # Bước 2: Chỉ gọi API khi thực sự cần thiết
        # Cần API khi:
        # - Kết quả không chắc chắn (UNKNOWN, RISKY)
        # - Hoặc là email miễn phí (Gmail, etc.) vì SMTP check không hiệu quả
        need_api = (
            free_data["deliverability"] in ["UNKNOWN", "RISKY"]
            or free_data["is_free_email"]["value"]
        )

        final_data = free_data
        if need_api:
            api_data = check_email_api(email)
            if api_data:
                # Nếu API thành công, lấy kết quả từ API làm kết quả cuối cùng
                final_data = api_data
        
        # Chuẩn hóa hiển thị (thêm .get để tránh lỗi nếu key không tồn tại)
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