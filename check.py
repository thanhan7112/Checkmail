import streamlit as st
import requests
import pandas as pd
import re
import smtplib
import socket
import dns.resolver
import random
import string
import time
import hashlib
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from threading import Lock
from datetime import datetime, timedelta

# ========== Cấu hình ==========
API_KEYS = [
    "c985842edb6f4049a6d0977928cdc4a7", "0d1f2b3d9f054a2e9fdd398ae019a76b",
    "2b88713468ba46bdb602c007da9d12cc", "a2f856614f2d41aca555a01df86b0599",
    "dd2b9a685420437f9933c1bf61889847", "2f0d37f98c6345818840dc31c14d2a75",
    "8017751baaea40a7918a299257ef90fb", "e6539e72e81c4c948a336a22c40d6565",
    "ee110d38f1d1461f820317426c4fd709", "73614f4f15a44082abb40c6d25feb13e",
    "a58021e0795b45e7bd3604f766d01809", "14d136c854034f6f95edb27d5264833d",
    "476bcc6eafa84f71abf10152e53c7e1f", "aee1766f20ee403ca90dc5dac23153e0",
    "8c81f01b09324dbf9966884b26759bb1", "e037ccc9293742f69499e1f48d86b5a6",
    "a2154fd4ad3a4205ac1dc3cb467c6731", "e6a17fed48f74e17bbfed885b34ccb5b",
    "a39ca210d21d43e9afa76495422e9108", "fb93a55588fb4e64ad49142f7189b8e3",
    "82b670414cf44344b60753934c11ce6d", "2b32c3f8d61d4bfda9aa467f23ebff95",
    "13babd98df194e8e8ec110809801ea0c", "8a2e57e6ce874e25bb19d74c22de90c3",
    "c37644932fc94de88c6720def64af036", "2e1413d074a44176a4bfd3aad9c67909",
    "acf19a0217fa45bd84dba57e340bdfc7", "26cbd3a7e3164ce49b65bdbf9d733a57",
    "b0e754fbeeff4c7ea800c86a5713f70d", "c8655ba9e0094e01acfb095cef4a7961",
    "0d263fe5f3e7467eabda50e119c90c78", "3085bcf9bc0d4be3a9bd3d20de43691e",
    "ce8ceec7c0da4e74a109bf7fb300e40f", "5a55a9e2802c4064b37c1397b8cfe1ba",
    "eee59da670144a1caea47114dce72bb7",
]
API_URL = "https://emailvalidation.abstractapi.com/v1/"

# Cache cho disposable domains từ API
DISPOSABLE_DOMAINS_CACHE = set()
DISPOSABLE_CACHE_TIME = None

def load_disposable_domains():
    """Tải danh sách disposable domains từ API"""
    global DISPOSABLE_DOMAINS_CACHE, DISPOSABLE_CACHE_TIME
    try:
        # Cache 24h
        if DISPOSABLE_CACHE_TIME and (datetime.now() - DISPOSABLE_CACHE_TIME) < timedelta(hours=24):
            return DISPOSABLE_DOMAINS_CACHE
        
        response = requests.get("https://disposable.debounce.io/?format=json", timeout=5)
        if response.status_code == 200:
            DISPOSABLE_DOMAINS_CACHE = set(response.json())
            DISPOSABLE_CACHE_TIME = datetime.now()
            return DISPOSABLE_DOMAINS_CACHE
    except:
        pass
    
    # Fallback nếu API lỗi
    return {"10minutemail.com", "temp-mail.org", "mailinator.com", "yopmail.com", "guerrillamail.com", "throwaway.email"}

def load_free_domains():
    """Danh sách free domains phổ biến"""
    return {
        "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com", "icloud.com",
        "mail.com", "yandex.com", "protonmail.com", "zoho.com", "gmx.com", "live.com",
        "msn.com", "yahoo.co.uk", "yahoo.fr", "yahoo.de", "googlemail.com", "me.com",
        "yahoo.co.jp", "yahoo.ca", "yahoo.com.au", "yahoo.co.in", "qq.com", "163.com",
        "126.com", "sina.com", "yeah.net", "foxmail.com", "mail.ru", "yandex.ru"
    }

def load_role_accounts():
    """Danh sách role accounts phổ biến"""
    return {
        "admin", "support", "info", "contact", "sales", "hr", "billing", "postmaster",
        "abuse", "noreply", "no-reply", "marketing", "hello", "help", "service",
        "team", "careers", "jobs", "press", "media", "webmaster", "hostmaster",
        "privacy", "security", "legal", "feedback", "newsletter", "notification"
    }

# Khởi tạo
FREE_DOMAINS = load_free_domains()
DISPOSABLE_DOMAINS = load_disposable_domains()
ROLE_ACCOUNTS = load_role_accounts()

# ========== Quản lý API Key với Rate Limiting và Fingerprint Rotation ==========
class APIKeyManager:
    def __init__(self, keys, min_interval=0.34):  # 3 req/s = ~0.33s/req, dùng 0.34 để an toàn
        self.keys = keys
        self.min_interval = min_interval
        self.key_states = {k: {"last_used": 0, "failed": False, "request_times": deque(maxlen=100)} for k in keys}
        self.lock = Lock()
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
        ]
        self.referers = [
            "https://www.google.com/",
            "https://www.bing.com/",
            "https://duckduckgo.com/",
            "https://github.com/",
            None  # Không có referer
        ]
    
    def _generate_fake_fingerprint(self, key):
        """Tạo fingerprint giả cho mỗi request"""
        seed = hashlib.md5(f"{key}{time.time()}{random.random()}".encode()).hexdigest()
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": random.choice(["en-US,en;q=0.9", "en-GB,en;q=0.8", "vi-VN,vi;q=0.9,en;q=0.8"]),
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": random.choice(self.referers),
            "DNT": random.choice(["1", None]),
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": random.choice(["same-origin", "cross-site", "none"]),
            "Cache-Control": random.choice(["no-cache", "max-age=0"]),
            "X-Request-ID": seed[:16],
        }
    
    def get_available_key(self):
        """Lấy key khả dụng với rate limiting"""
        with self.lock:
            now = time.time()
            available_keys = [k for k, s in self.key_states.items() if not s["failed"] and (now - s["last_used"]) >= self.min_interval]
            
            if not available_keys:
                # Đợi key nhanh nhất available
                wait_times = [(k, self.min_interval - (now - s["last_used"])) for k, s in self.key_states.items() if not s["failed"]]
                if wait_times:
                    wait_times.sort(key=lambda x: x[1])
                    key, wait_time = wait_times[0]
                    if wait_time > 0:
                        time.sleep(wait_time)
                    return key
                return None
            
            # Chọn key ngẫu nhiên trong số available để tránh pattern
            return random.choice(available_keys)
    
    def mark_key_used(self, key):
        """Đánh dấu key đã được sử dụng"""
        with self.lock:
            self.key_states[key]["last_used"] = time.time()
            self.key_states[key]["request_times"].append(time.time())
    
    def mark_key_failed(self, key):
        """Đánh dấu key bị lỗi"""
        with self.lock:
            self.key_states[key]["failed"] = True
    
    def get_stats(self):
        """Lấy thống kê key"""
        with self.lock:
            active = sum(1 for s in self.key_states.values() if not s["failed"])
            failed = len(self.keys) - active
            return {"active": active, "failed": failed, "total": len(self.keys)}

key_manager = APIKeyManager(API_KEYS)

# ========== Kiểm tra API Key còn hoạt động ==========
def check_api_key_status(key):
    """Kiểm tra key còn hoạt động không"""
    try:
        headers = key_manager._generate_fake_fingerprint(key)
        headers = {k: v for k, v in headers.items() if v is not None}
        
        # Dùng email test đơn giản
        response = requests.get(
            API_URL,
            params={"api_key": key, "email": "test@gmail.com"},
            headers=headers,
            timeout=8,
            allow_redirects=True
        )
        
        if response.status_code == 200:
            return True, "✅ Hoạt động"
        elif response.status_code == 401:
            return False, "❌ Hết hạn/Vô hiệu"
        elif response.status_code == 429:
            return True, "⚠️ Rate limit (vẫn hoạt động)"
        else:
            return None, f"⚠️ Mã lỗi: {response.status_code}"
    except Exception as e:
        return None, f"❌ Lỗi: {str(e)[:50]}"

# ========== Hàm gọi API với anti-detection ==========
def check_email_api(email):
    """Gọi API với fingerprint giả và rate limiting"""
    max_retries = 3
    
    for attempt in range(max_retries):
        key = key_manager.get_available_key()
        if not key:
            time.sleep(0.5)
            continue
        
        try:
            # Tạo headers giả cho request này
            headers = key_manager._generate_fake_fingerprint(key)
            headers = {k: v for k, v in headers.items() if v is not None}
            
            # Thêm jitter nhỏ để tránh pattern nhận diện
            time.sleep(random.uniform(0.01, 0.05))
            
            response = requests.get(
                API_URL,
                params={"api_key": key, "email": email},
                headers=headers,
                timeout=10,
                allow_redirects=True
            )
            
            key_manager.mark_key_used(key)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                key_manager.mark_key_failed(key)
                continue
            elif response.status_code == 429:
                # Rate limited, đợi và thử key khác
                time.sleep(0.5)
                continue
            else:
                continue
                
        except requests.exceptions.RequestException:
            continue
    
    return None

# ========== Các hàm kiểm tra email (giữ nguyên) ==========
def get_mx_records_robust(domain):
    try:
        records = dns.resolver.resolve(domain, 'MX')
        return sorted([(r.preference, r.exchange.to_text()) for r in records])
    except:
        try:
            r = requests.get(f"https://dns.google/resolve?name={domain}&type=MX", timeout=5)
            r.raise_for_status()
            data = r.json()
            if "Answer" in data:
                answers = sorted([ans["data"].split() for ans in data.get("Answer", []) if ans.get("type") == 15], key=lambda x: int(x[0]))
                return [(int(p), ex) for p, ex in answers]
        except:
            pass
    return []

def check_email_free_super_advanced(email):
    result = {"email": email, "deliverability": "UNKNOWN", "is_valid_format": {"value": False}, 
              "is_free_email": {"value": False}, "is_disposable_email": {"value": False}, 
              "is_role_email": {"value": False}, "is_catchall_email": {"value": False}, 
              "is_mx_found": {"value": False}, "is_smtp_valid": {"value": False, "text": "UNKNOWN"}}
    
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_valid_format"]["value"] = True
    
    local_part, domain = email.split("@")
    if domain in FREE_DOMAINS:
        result["is_free_email"]["value"] = True
    
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable_email"]["value"] = True
        result["deliverability"] = "UNDELIVERABLE"
        return result
    
    if local_part.lower() in ROLE_ACCOUNTS:
        result["is_role_email"]["value"] = True
    
    mx_records = get_mx_records_robust(domain)
    if not mx_records:
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_mx_found"]["value"] = True
    
    if result["is_free_email"]["value"]:
        result["deliverability"] = "DELIVERABLE"
        result["is_smtp_valid"]["value"] = True
        return result
    
    for _, mx_record in mx_records:
        try:
            with smtplib.SMTP(mx_record, 25, timeout=15) as server:
                server.set_debuglevel(0)
                hostname = socket.getfqdn() or 'example.com'
                server.ehlo(hostname)
                if server.has_extn('starttls'):
                    server.starttls()
                    server.ehlo(hostname)
                server.mail(f'verify@{hostname}')
                code, _ = server.rcpt(str(email))
                
                if code == 250:
                    result["is_smtp_valid"]["value"] = True
                    result["deliverability"] = "DELIVERABLE"
                    random_local = ''.join(random.choice(string.ascii_lowercase) for _ in range(20))
                    code_catchall, _ = server.rcpt(f"{random_local}@{domain}")
                    if code_catchall == 250:
                        result["is_catchall_email"]["value"] = True
                        result["deliverability"] = "RISKY"
                    return result
                elif 450 <= code <= 452:
                    result["deliverability"] = "RISKY"
                    result["is_smtp_valid"]["text"] = "GREYLISTED"
                elif code >= 500:
                    result["deliverability"] = "RISKY"
                    result["is_smtp_valid"]["text"] = "SMTP_REJECTION"
                    return result
        except:
            continue
    
    return result

def map_result_to_status(result):
    deliverability = result.get("deliverability", "UNKNOWN").upper()
    is_disposable = result.get("is_disposable_email", {}).get("value", False)
    is_valid_format = result.get("is_valid_format", {}).get("value", False)
    if not is_valid_format:
        return "❌ Sai định dạng"
    if is_disposable:
        return "🗑️ Email tạm thời"
    if deliverability == "DELIVERABLE":
        return "✅ Hợp lệ"
    elif deliverability == "UNDELIVERABLE":
        return "🚫 Không hợp lệ"
    elif deliverability == "RISKY":
        return "⚠️ Rủi ro (Tự động xác thực lại)"
    else:
        return "❓ Không xác định"

def process_email_task(email):
    final_data = check_email_free_super_advanced(email)
    is_risky = final_data["deliverability"] in ["UNKNOWN", "RISKY"]
    is_free = final_data.get("is_free_email", {}).get("value", False)
    if is_risky or is_free:
        api_data = check_email_api(email)
        if api_data:
            final_data = api_data
    status = map_result_to_status(final_data)
    return status

# ========== GIAO DIỆN STREAMLIT ==========
st.set_page_config(page_title="Công cụ kiểm tra Email hàng loạt", layout="wide")
st.title("📧 Công cụ kiểm tra Email hàng loạt - Tối ưu Anti-Detection")

# Hiển thị thống kê key
stats = key_manager.get_stats()
col1, col2, col3 = st.columns(3)
col1.metric("API Keys hoạt động", stats["active"], delta=None)
col2.metric("API Keys lỗi", stats["failed"], delta=None if stats["failed"] == 0 else f"-{stats['failed']}")
col3.metric("Rate Limit", f"{1/key_manager.min_interval:.1f} req/s/key")

# Nút kiểm tra tất cả key
if st.button("🔍 Kiểm tra trạng thái tất cả API Keys", use_container_width=True):
    with st.spinner("Đang kiểm tra..."):
        results = []
        for i, key in enumerate(API_KEYS):
            status, msg = check_api_key_status(key)
            results.append({"Key": f"Key #{i+1}", "Trạng thái": msg, "Mã key": key[:8] + "..."})
            time.sleep(0.4)  # Tránh spam API
        st.dataframe(pd.DataFrame(results), use_container_width=True)

st.divider()

tab1, tab2 = st.tabs(["📁 Tải lên File (Excel/CSV)", "✍️ Nhập thủ công"])

with tab1:
    st.header("1. Tải lên file của bạn")
    uploaded_file = st.file_uploader("Chọn file .xlsx hoặc .csv", type=["xlsx", "csv"])
    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
            st.info(f"Đã tải lên: **{uploaded_file.name}** với **{len(df)}** dòng.")
            st.dataframe(df.head(), use_container_width=True)
            st.header("2. Chọn cột chứa email")
            email_column = st.selectbox("Chọn tên cột email:", df.columns, index=None, placeholder="-- Chọn một cột --")
            if email_column:
                st.header("3. Bắt đầu kiểm tra")
                if st.button("🚀 Bắt đầu kiểm tra file", key="file_check", use_container_width=True):
                    total_rows = len(df)
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    results_status = [""] * total_rows

                    email_tasks = []
                    for i, row in df.iterrows():
                        email_to_check = None
                        raw_cell_value = row[email_column]
                        if isinstance(raw_cell_value, str) and raw_cell_value.strip():
                            possible_emails = re.split('[,;\s]+', raw_cell_value)
                            for email_candidate in possible_emails:
                                if email_candidate and '@' in email_candidate:
                                    email_to_check = email_candidate.strip()
                                    break
                        if not email_to_check:
                            results_status[i] = "Trống / Không có email hợp lệ"
                        else:
                            email_tasks.append((i, email_to_check))

                    completed = 0
                    if email_tasks:
                        status_text.text(f"⚙️ Đang kiểm tra {len(email_tasks)} email với {MAX_WORKERS} luồng...")
                        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                            future_to_index = {executor.submit(process_email_task, email): idx for idx, email in email_tasks}
                            for fut in as_completed(future_to_index):
                                idx = future_to_index[fut]
                                try:
                                    res_status = fut.result()
                                except Exception as e:
                                    res_status = f"❗ Lỗi: {str(e)[:30]}"
                                results_status[idx] = res_status
                                completed += 1
                                progress_bar.progress(sum(1 for r in results_status if r) / total_rows)
                                status_text.text(f"⚙️ Đã hoàn thành {completed}/{len(email_tasks)} email...")
                    
                    progress_bar.progress(1.0)
                    status_text.success("🎉 Hoàn thành kiểm tra file!")
                    df_result = df.copy()
                    df_result["Tình trạng xác thực"] = results_status
                    st.subheader("Kết quả (10 dòng đầu)")
                    st.dataframe(df_result.head(10), use_container_width=True)
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        df_result.to_excel(writer, index=False, sheet_name="Kết quả")
                    st.download_button("📥 Tải về kết quả", data=output.getvalue(), file_name=f"ket_qua_{uploaded_file.name}", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except Exception as e:
            st.error(f"Lỗi: {e}")

with tab2:
    st.header("Nhập danh sách email (mỗi email một dòng)")
    emails_input = st.text_area("Danh sách email:", height=250, placeholder="example@gmail.com\nsupport@company.com", label_visibility="collapsed")
    if st.button("Kiểm tra danh sách nhập tay", key="manual_check", use_container_width=True):
        emails = [e.strip().lower() for e in emails_input.splitlines() if e.strip()]
        if not emails:
            st.warning("Vui lòng nhập ít nhất một email.")
        else:
            total = len(emails)
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = [None] * total

            completed = 0
            status_text.text(f"⚙️ Đang kiểm tra {total} email với {MAX_WORKERS} luồng...")
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_idx = {executor.submit(process_email_task, email): i for i, email in enumerate(emails)}
                for fut in as_completed(future_to_idx):
                    i = future_to_idx[fut]
                    try:
                        res_status = fut.result()
                    except Exception as e:
                        res_status = f"❗ Lỗi: {str(e)[:30]}"
                    results[i] = {"Email": emails[i], "Trạng thái": res_status}
                    completed += 1
                    progress_bar.progress(completed / total)
                    status_text.text(f"⚙️ Đã hoàn thành {completed}/{total} email...")
            status_text.success("🎉 Hoàn thành!")
            st.dataframe(pd.DataFrame(results), use_container_width=True)
