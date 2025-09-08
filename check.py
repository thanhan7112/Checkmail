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
API_URL = "https://emailvalidation.abstractapi.com/v1/"

# Các danh sách tên miền và tài khoản vai trò
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

# ==============================================================================
# ==========               CÁC HÀM KIỂM TRA EMAIL               ==========
# ==============================================================================

# ---------- 1. Kiểm tra bằng Abstract API (Dùng khi cần độ chính xác cao) ----------
def check_email_api(email):
    """Gửi yêu cầu đến Abstract API để xác thực email."""
    for api_key in API_KEYS:
        try:
            response = requests.get(
                API_URL,
                params={"api_key": api_key, "email": email},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                # Key không hợp lệ hoặc hết hạn, thử key tiếp theo
                continue
        except requests.exceptions.RequestException:
            # Lỗi mạng hoặc timeout, thử key tiếp theo
            continue
    return None

# ---------- 2. Lấy MX record (Phương pháp nâng cao) ----------
def get_mx_records_robust(domain):
    """
    Lấy bản ghi MX của một tên miền.
    Ưu tiên sử dụng thư viện dnspython, nếu thất bại sẽ dùng Google DNS API làm dự phòng.
    """
    # Cách 1: Dùng dnspython (chính thống và đáng tin cậy hơn)
    try:
        records = dns.resolver.resolve(domain, 'MX')
        # Sắp xếp theo mức độ ưu tiên (số nhỏ hơn = ưu tiên cao hơn)
        mx_records = sorted([(r.preference, r.exchange.to_text()) for r in records])
        return mx_records
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout):
        # Cách 2: Dự phòng bằng Google DNS API
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
        except requests.exceptions.RequestException:
            return []
    except Exception:
        return []

# ---------- 3. Kiểm tra miễn phí nâng cao (Cải tiến) ----------
def check_email_free_super_advanced(email):
    """
    Thực hiện kiểm tra email nhiều bước mà không cần API.
    Bao gồm: Regex, loại domain, MX record, và kiểm tra SMTP nâng cao (phát hiện catch-all).
    """
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

    # Bước 1: Kiểm tra định dạng bằng Regex
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_valid_format"] = {"value": True, "text": "TRUE"}

    local_part, domain = email.split("@")

    # Bước 2: Phân loại email dựa trên danh sách có sẵn
    if domain in FREE_DOMAINS:
        result["is_free_email"] = {"value": True, "text": "TRUE"}
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable_email"] = {"value": True, "text": "TRUE"}
        result["deliverability"] = "UNDELIVERABLE"
        return result
    if local_part.lower() in ROLE_ACCOUNTS:
        result["is_role_email"] = {"value": True, "text": "TRUE"}

    # Bước 3: Tìm kiếm bản ghi MX
    mx_records = get_mx_records_robust(domain)
    if not mx_records:
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_mx_found"] = {"value": True, "text": "TRUE"}

    # Tạm tin tưởng các nhà cung cấp email miễn phí lớn vì họ thường chặn kiểm tra SMTP
    if result["is_free_email"]["value"]:
        result["deliverability"] = "DELIVERABLE"
        result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
        return result

    # Bước 4: Kiểm tra SMTP nâng cao
    for _, mx_record in mx_records:
        try:
            with smtplib.SMTP(mx_record, 25, timeout=10) as server:
                server.set_debuglevel(0)
                hostname = socket.getfqdn() or 'example.com'
                server.ehlo(hostname)
                server.mail(f'verify@{hostname}')
                
                # Kiểm tra email thật
                code, _ = server.rcpt(str(email))
                
                if code == 250: # Mã 250: OK, email tồn tại
                    result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
                    result["deliverability"] = "DELIVERABLE"

                    # --> Bắt đầu kiểm tra Catch-all <--
                    random_local = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(20))
                    random_email = f"{random_local}@{domain}"
                    code_catchall, _ = server.rcpt(random_email)
                    
                    if code_catchall == 250:
                        result["is_catchall_email"] = {"value": True, "text": "TRUE"}
                        result["deliverability"] = "RISKY"
                    else:
                        result["is_catchall_email"] = {"value": False, "text": "FALSE"}
                    
                    return result # Đã có kết quả, thoát hoàn toàn

                elif code >= 500: # Mã 5xx: Lỗi vĩnh viễn, email không tồn tại
                    result["is_smtp_valid"] = {"value": False, "text": "FALSE"}
                    result["deliverability"] = "UNDELIVERABLE"
                    return result
                
                # Nếu mã là 4xx (lỗi tạm thời), ta không làm gì và để vòng lặp thử MX record tiếp theo

        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, socket.timeout):
            continue # Lỗi kết nối, thử MX record tiếp theo
        except Exception:
            result["deliverability"] = "UNKNOWN" # Lỗi không xác định, dừng lại
            return result
            
    return result

# ==============================================================================
# ==========                  GIAO DIỆN STREAMLIT                 ==========
# ==============================================================================

st.set_page_config(page_title="Công cụ kiểm tra Email", layout="wide", initial_sidebar_state="collapsed")
st.title("📧 Công cụ kiểm tra Email (Phiên bản nâng cấp)")

st.info(
    "**Cách hoạt động:** Công cụ này kết hợp phương pháp kiểm tra miễn phí (Regex, MX, SMTP) và API trả phí.\n"
    "1.  **Kiểm tra miễn phí trước:** Nhanh chóng loại bỏ các email sai định dạng, không có máy chủ hoặc tạm thời.\n"
    "2.  **Dùng API khi cần:** Đối với các trường hợp khó (`UNKNOWN`, `RISKY`) hoặc các email miễn phí (Gmail, Outlook,...), công cụ sẽ gọi API để có kết quả chính xác nhất."
)

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

            # Luôn chạy kiểm tra miễn phí trước
            final_data = check_email_free_super_advanced(email)

            # Quyết định có cần dùng API hay không
            is_risky = final_data["deliverability"] in ["UNKNOWN", "RISKY"]
            is_free = final_data["is_free_email"]["value"]
            
            if is_risky or is_free:
                status_text.text(f"⚙️ Đang kiểm tra: {email} ({i+1}/{len(emails)}) - Cần xác thực sâu hơn, đang dùng API...")
                api_data = check_email_api(email)
                if api_data:
                    # Nếu API thành công, dùng kết quả của API
                    final_data = api_data
            
            # Chuẩn hóa dữ liệu để hiển thị
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

        # Chức năng tải về
        st.subheader("Tải về kết quả")
        col1, col2 = st.columns(2)

        # Tải về CSV
        csv = df.to_csv(index=False).encode("utf-8")
        with col1:
            st.download_button(
                label="📥 Tải về file CSV",
                data=csv,
                file_name="ket_qua_kiem_tra_email.csv",
                mime="text/csv",
                use_container_width=True,
            )

        # Tải về Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Kết quả")
        
        with col2:
            st.download_button(
                label="📥 Tải về file Excel",
                data=output.getvalue(),
                file_name="ket_qua_kiem_tra_email.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
