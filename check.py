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
FREE_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com", "icloud.com", "mail.com", "yandex.com", "protonmail.com"}
DISPOSABLE_DOMAINS = {"10minutemail.com", "temp-mail.org", "mailinator.com", "yopmail.com", "guerrillamail.com"}
ROLE_ACCOUNTS = {"admin", "support", "info", "contact", "sales", "hr", "billing", "postmaster", "abuse", "noreply", "marketing"}

# ==============================================================================
# ==========               CÁC HÀM KIỂM TRA EMAIL               ==========
# ==============================================================================
# (Các hàm check_email_api, get_mx_records_robust, check_email_free_super_advanced giữ nguyên như cũ)
def check_email_api(email):
    for api_key in API_KEYS:
        try:
            response = requests.get(API_URL, params={"api_key": api_key, "email": email}, timeout=10)
            if response.status_code == 200: return response.json()
            elif response.status_code == 401: continue
        except requests.exceptions.RequestException: continue
    return None

def get_mx_records_robust(domain):
    try:
        records = dns.resolver.resolve(domain, 'MX')
        return sorted([(r.preference, r.exchange.to_text()) for r in records])
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout):
        try:
            r = requests.get(f"https://dns.google/resolve?name={domain}&type=MX", timeout=5)
            r.raise_for_status()
            data = r.json()
            if "Answer" in data:
                answers = sorted([ans["data"].split() for ans in data.get("Answer", []) if ans.get("type") == 15], key=lambda x: int(x[0]))
                return [(int(p), ex) for p, ex in answers]
        except requests.exceptions.RequestException: pass
    except Exception: pass
    return []

def check_email_free_super_advanced(email):
    result = {"email": email, "deliverability": "UNKNOWN", "is_valid_format": {"value": False}, "is_free_email": {"value": False}, "is_disposable_email": {"value": False}, "is_role_email": {"value": False}, "is_catchall_email": {"value": False}, "is_mx_found": {"value": False}, "is_smtp_valid": {"value": False, "text": "UNKNOWN"}}
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        result["deliverability"] = "UNDELIVERABLE"; return result
    result["is_valid_format"]["value"] = True
    local_part, domain = email.split("@")
    if domain in FREE_DOMAINS: result["is_free_email"]["value"] = True
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable_email"]["value"] = True; result["deliverability"] = "UNDELIVERABLE"; return result
    if local_part.lower() in ROLE_ACCOUNTS: result["is_role_email"]["value"] = True
    mx_records = get_mx_records_robust(domain)
    if not mx_records:
        result["deliverability"] = "UNDELIVERABLE"; return result
    result["is_mx_found"]["value"] = True
    if result["is_free_email"]["value"]:
        result["deliverability"] = "DELIVERABLE"; result["is_smtp_valid"]["value"] = True; return result
    for _, mx_record in mx_records:
        try:
            with smtplib.SMTP(mx_record, 25, timeout=15) as server:
                server.set_debuglevel(0)
                hostname = socket.getfqdn() or 'example.com'
                server.ehlo(hostname)
                if server.has_extn('starttls'):
                    server.starttls(); server.ehlo(hostname)
                server.mail(f'verify@{hostname}')
                code, _ = server.rcpt(str(email))
                if code == 250:
                    result["is_smtp_valid"]["value"] = True; result["deliverability"] = "DELIVERABLE"
                    random_local = ''.join(random.choice(string.ascii_lowercase) for _ in range(20))
                    code_catchall, _ = server.rcpt(f"{random_local}@{domain}")
                    if code_catchall == 250:
                        result["is_catchall_email"]["value"] = True; result["deliverability"] = "RISKY"
                    return result
                elif 450 <= code <= 452:
                    result["deliverability"] = "RISKY"; result["is_smtp_valid"]["text"] = "GREYLISTED"
                elif code >= 500:
                    result["deliverability"] = "UNDELIVERABLE"; return result
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, socket.timeout): continue
        except Exception: continue
    return result

# ==============================================================================
# ==========                  GIAO DIỆN STREAMLIT                 ==========
# ==============================================================================

st.set_page_config(page_title="Công cụ kiểm tra Email hàng loạt", layout="wide")
st.title("📧 Công cụ kiểm tra Email hàng loạt từ File Excel/CSV")

def map_result_to_status(result):
    deliverability = result.get("deliverability", "UNKNOWN").upper()
    is_disposable = result.get("is_disposable_email", {}).get("value", False)
    is_valid_format = result.get("is_valid_format", {}).get("value", False)
    if not is_valid_format: return "❌ Sai định dạng"
    if is_disposable: return "🗑️ Email tạm thời"
    if deliverability == "DELIVERABLE": return "✅ Hợp lệ"
    elif deliverability == "UNDELIVERABLE": return "🚫 Không hợp lệ"
    elif deliverability == "RISKY": return "⚠️ Rủi ro (Catch-all/Greylisted)"
    else: return "❓ Không xác định"

tab1, tab2 = st.tabs(["📁 Tải lên File (Excel/CSV)", "✍️ Nhập thủ công"])

with tab1:
    st.header("1. Tải lên file của bạn")
    uploaded_file = st.file_uploader("Chọn file .xlsx hoặc .csv", type=["xlsx", "csv"])
    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
            st.info(f"Đã tải lên file: **{uploaded_file.name}** với **{len(df)}** dòng.")
            st.dataframe(df.head(), use_container_width=True)
            st.header("2. Chọn cột chứa email")
            email_column = st.selectbox("Chọn tên cột email từ file của bạn:", df.columns, index=None, placeholder="-- Chọn một cột --")
            if email_column:
                st.header("3. Bắt đầu kiểm tra")
                if st.button("🚀 Bắt đầu kiểm tra file", key="file_check", use_container_width=True):
                    results_status = []
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    total_rows = len(df)
                    
                    for i, row in df.iterrows():
                        # ==================== PHẦN MÃ ĐƯỢC CẬP NHẬT ====================
                        email_to_check = None
                        raw_cell_value = row[email_column]

                        # Chỉ xử lý nếu ô không trống và là dạng chuỗi
                        if isinstance(raw_cell_value, str) and raw_cell_value.strip():
                            # Tách chuỗi bằng dấu phẩy, chấm phẩy hoặc khoảng trắng
                            possible_emails = re.split('[,;\s]+', raw_cell_value)
                            
                            # Tìm email hợp lệ đầu tiên trong danh sách đã tách
                            for email_candidate in possible_emails:
                                if email_candidate and '@' in email_candidate:
                                    email_to_check = email_candidate.strip()
                                    break # Dừng lại ngay khi tìm thấy email đầu tiên
                        
                        status_text.text(f"⚙️ Đang xử lý dòng {i+1}/{total_rows}...")
                        
                        if not email_to_check:
                            results_status.append("Trống / Không có email hợp lệ")
                        else:
                            # Chạy logic kiểm tra với email đã được làm sạch
                            final_data = check_email_free_super_advanced(email_to_check)
                            is_risky = final_data["deliverability"] in ["UNKNOWN", "RISKY"]
                            is_free = final_data.get("is_free_email", {}).get("value", False)
                            
                            if is_risky or is_free:
                                api_data = check_email_api(email_to_check)
                                if api_data:
                                    final_data = api_data
                            
                            status = map_result_to_status(final_data)
                            results_status.append(status)
                        # ==================== KẾT THÚC PHẦN CẬP NHẬT =====================
                        
                        progress_bar.progress((i + 1) / total_rows)

                    status_text.success("🎉 Hoàn thành kiểm tra file!")
                    df_result = df.copy()
                    df_result["Tình trạng xác thực"] = results_status
                    st.subheader("Kết quả kiểm tra (xem trước 10 dòng đầu)")
                    st.dataframe(df_result.head(10), use_container_width=True)
                    
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        df_result.to_excel(writer, index=False, sheet_name="Kết quả xác thực")
                    
                    st.download_button(
                        label="📥 Tải về file Excel kết quả",
                        data=output.getvalue(),
                        file_name=f"ket_qua_{uploaded_file.name}",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
        except Exception as e:
            st.error(f"Đã xảy ra lỗi khi đọc hoặc xử lý file: {e}")

with tab2:
    st.header("Nhập danh sách email (mỗi email một dòng)")
    emails_input = st.text_area("Danh sách email:", height=250, placeholder="example@gmail.com\nsupport@company.com\n...", label_visibility="collapsed")
    if st.button("Kiểm tra danh sách nhập tay", key="manual_check", use_container_width=True):
        emails = [e.strip().lower() for e in emails_input.splitlines() if e.strip()]
        if not emails:
            st.warning("Vui lòng nhập ít nhất một email.")
        else:
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            for i, email in enumerate(emails):
                status_text.text(f"⚙️ Đang kiểm tra: {email} ({i+1}/{len(emails)})")
                final_data = check_email_free_super_advanced(email)
                is_risky = final_data["deliverability"] in ["UNKNOWN", "RISKY"]
                is_free = final_data.get("is_free_email", {}).get("value", False)
                if is_risky or is_free:
                    api_data = check_email_api(email)
                    if api_data:
                        final_data = api_data
                results.append({"Email": email, "Trạng thái": map_result_to_status(final_data)})
                progress_bar.progress((i + 1) / len(emails))
            status_text.success("🎉 Hoàn thành!")
            st.dataframe(pd.DataFrame(results), use_container_width=True)
