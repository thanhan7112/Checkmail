import streamlit as st
import requests
import pandas as pd
import re
import smtplib
import socket
import random
import string
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

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
    "8c81f01b09324dbf9966884b26759bb1",
    "e037ccc9293742f69499e1f48d86b5a6",
    "a2154fd4ad3a4205ac1dc3cb467c6731",
    "e6a17fed48f74e17bbfed885b34ccb5b",
    "a39ca210d21d43e9afa76495422e9108",
    "fb93a55588fb4e64ad49142f7189b8e3",
    "82b670414cf44344b60753934c11ce6d",
    "2b32c3f8d61d4bfda9aa467f23ebff95",
    "13babd98df194e8e8ec110809801ea0c",
    "8a2e57e6ce874e25bb19d74c22de90c3",
    "c37644932fc94de88c6720def64af036",
    "2e1413d074a44176a4bfd3aad9c67909",
    "acf19a0217fa45bd84dba57e340bdfc7",
    "26cbd3a7e3164ce49b65bdbf9d733a57",
    "b0e754fbeeff4c7ea800c86a5713f70d",
    "c8655ba9e0094e01acfb095cef4a7961",
    "0d263fe5f3e7467eabda50e119c90c78",
    "3085bcf9bc0d4be3a9bd3d20de43691e",
    "ce8ceec7c0da4e74a109bf7fb300e40f",
    "5a55a9e2802c4064b37c1397b8cfe1ba",
    "eee59da670144a1caea47114dce72bb7",
]

API_URL = "https://emailvalidation.abstractapi.com/v1/"

FREE_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com", "icloud.com", "mail.com", "yandex.com", "protonmail.com"}
DISPOSABLE_DOMAINS = {"10minutemail.com", "temp-mail.org", "mailinator.com", "yopmail.com", "guerrillamail.com"}
ROLE_ACCOUNTS = {"admin", "support", "info", "contact", "sales", "hr", "billing", "postmaster", "abuse", "noreply", "marketing"}

# ========== QUẢN LÝ API KEY VỚI RATE LIMIT ==========
class ApiKeyManager:
    """
    Quản lý xoay vòng API key và đảm bảo mỗi key không bị gọi quá nhanh.
    - keys: list các API key
    - min_interval_ms: khoảng tối thiểu giữa 2 request trên cùng 1 key (ms)
    """
    def __init__(self, keys, min_interval_ms=500):
        self.keys = list(keys)
        self.min_interval_ms = min_interval_ms
        self.lock = threading.Lock()
        # last used timestamp per key (epoch seconds)
        self.last_used = {k: 0.0 for k in self.keys}
        self.index = 0

    def get_key(self, wait_if_needed=True, timeout=5.0):
        """
        Trả về (key, wait_ms) hoặc (None, None) nếu không lấy được key trong timeout.
        Nếu wait_if_needed=True sẽ chờ 1 khoảng nhỏ nếu key gần đây vừa dùng.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                if not self.keys:
                    return None
                # thử xoay từ current index
                for _ in range(len(self.keys)):
                    key = self.keys[self.index % len(self.keys)]
                    self.index += 1
                    last = self.last_used.get(key, 0.0)
                    elapsed_ms = (time.time() - last) * 1000.0
                    if elapsed_ms >= self.min_interval_ms:
                        # mark used now and trả về
                        self.last_used[key] = time.time()
                        return key
                # nếu không có key sẵn sàng, break lock và chờ
            # chờ 50ms trước khi thử lại
            time.sleep(0.05)
        return None

# tạo manager mặc định (min interval 500ms/key)
api_key_manager = ApiKeyManager(API_KEYS, min_interval_ms=500)

# ========== SEMAPHORE / LIMITS (các giá trị mặc định có thể override từ UI) ==========
# Các semaphore sẽ được khởi tạo lại khi user bắt đầu chạy (từ các tùy chọn UI)
SMTP_SEMAPHORE = None
API_SEMAPHORE = None

# ========== HÀM GỌI ABSTRACT API (sử dụng ApiKeyManager & API_SEMAPHORE) ==========
def check_email_api(email, session=None):
    """
    Gọi AbstractAPI với giới hạn concurrency (API_SEMAPHORE) và rate-limit per key (ApiKeyManager).
    Trả về JSON nếu OK, hoặc None nếu tất cả thất bại.
    """
    global API_SEMAPHORE, api_key_manager
    if session is None:
        session = requests.Session()

    # nếu không có semaphore (chưa cấu hình), fallback không giới hạn
    if API_SEMAPHORE is None:
        api_semaphore_acquired = False
    else:
        api_semaphore_acquired = API_SEMAPHORE.acquire(timeout=10)

    try:
        # Lấy key từ manager (get_key sẽ chịu trách nhiệm delay nếu cần)
        key = api_key_manager.get_key(wait_if_needed=True, timeout=10.0)
        if not key:
            return None
        params = {"api_key": key, "email": email}
        # dùng requests session
        try:
            r = session.get(API_URL, params=params, timeout=12)
            if r is None:
                return None
            if r.status_code == 200:
                return r.json()
            # nếu 401 hoặc lỗi khác -> trả None để caller quyết định
            return None
        except Exception:
            return None
    finally:
        if api_semaphore_acquired:
            API_SEMAPHORE.release()

# ========== HÀM GET MX (dùng Google DNS HTTP) ==========
def get_mx_records(domain, session=None):
    if session is None:
        session = requests.Session()
    try:
        r = session.get(f"https://dns.google/resolve?name={domain}&type=MX", timeout=5)
        if r is None:
            return []
        data = r.json()
        if "Answer" in data:
            answers = []
            for ans in data.get("Answer", []):
                if ans.get("type") == 15:
                    parts = ans["data"].split()
                    if len(parts) >= 2:
                        pref = int(parts[0]); exch = parts[1]
                        answers.append((pref, exch.rstrip('.')))
            answers.sort(key=lambda x: x[0])
            return answers
    except Exception:
        return []
    return []

# ========== FREE CHECK (Regex + MX + SMTP) ========== 
def check_email_free(email, session=None):
    if session is None:
        session = requests.Session()
    result = {
        "email": email,
        "deliverability": "UNKNOWN",
        "is_valid_format": {"value": False},
        "is_free_email": {"value": False},
        "is_disposable_email": {"value": False},
        "is_role_email": {"value": False},
        "is_catchall_email": {"value": False},
        "is_mx_found": {"value": False},
        "is_smtp_valid": {"value": False, "text": "UNKNOWN"},
    }
    # Regex
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_valid_format"]["value"] = True

    local, domain = email.split("@", 1)
    domain = domain.lower()
    if domain in FREE_DOMAINS:
        result["is_free_email"]["value"] = True
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable_email"]["value"] = True
        result["deliverability"] = "UNDELIVERABLE"
        return result
    if local.lower() in ROLE_ACCOUNTS:
        result["is_role_email"]["value"] = True

    mx_records = get_mx_records(domain, session=session)
    if not mx_records:
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_mx_found"]["value"] = True

    if result["is_free_email"]["value"]:
        result["deliverability"] = "DELIVERABLE"
        result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
        return result

    # SMTP check — chú ý: giới hạn đồng thời bằng SMTP_SEMAPHORE (khởi tạo ở runtime)
    global SMTP_SEMAPHORE
    for _, mx in mx_records:
        mx_host = mx
        # acquire semaphore (nếu có)
        acquired = SMTP_SEMAPHORE.acquire(timeout=20) if SMTP_SEMAPHORE is not None else True
        try:
            try:
                with smtplib.SMTP(mx_host, 25, timeout=15) as server:
                    server.set_debuglevel(0)
                    hostname = socket.getfqdn() or "example.com"
                    server.ehlo(hostname)
                    if server.has_extn("starttls"):
                        try:
                            server.starttls(); server.ehlo(hostname)
                        except Exception:
                            pass
                    try:
                        server.mail(f"verify@{hostname}")
                    except Exception:
                        pass
                    code, _ = server.rcpt(email)
                    if code == 250:
                        result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
                        result["deliverability"] = "DELIVERABLE"
                        # catch-all check
                        try:
                            random_local = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(16))
                            code2, _ = server.rcpt(f"{random_local}@{domain}")
                            if code2 == 250:
                                result["is_catchall_email"] = {"value": True, "text": "TRUE"}
                                result["deliverability"] = "RISKY"
                            else:
                                result["is_catchall_email"] = {"value": False, "text": "FALSE"}
                        except Exception:
                            result["is_catchall_email"] = {"value": False, "text": "UNKNOWN"}
                        return result
                    elif 450 <= code <= 452:
                        result["deliverability"] = "RISKY"
                        result["is_smtp_valid"]["text"] = "GREYLISTED"
                        continue
                    elif code >= 500:
                        result["deliverability"] = "RISKY"
                        result["is_smtp_valid"]["text"] = "SMTP_REJECTION"
                        return result
                    else:
                        result["deliverability"] = "RISKY"
                        continue
            except Exception:
                continue
        finally:
            if SMTP_SEMAPHORE is not None and acquired:
                SMTP_SEMAPHORE.release()
    return result

# ========== WORKER xử lý 1 email ==========
def process_email(email, session=None):
    if session is None:
        session = requests.Session()
    try:
        free_res = check_email_free(email, session=session)
    except Exception:
        free_res = {"email": email, "deliverability": "UNKNOWN", "is_valid_format": {"value": False}, "is_free_email": {"value": False}}
    need_api = (free_res.get("deliverability") in ["UNKNOWN", "RISKY"]) or free_res.get("is_free_email", {}).get("value", False)
    final = free_res
    if need_api:
        api_res = check_email_api(email, session=session)
        if api_res:
            final = api_res
    # map result
    status_raw = final.get("deliverability", "UNKNOWN")
    is_valid_fmt = final.get("is_valid_format", {}).get("value", False)
    is_disposable = final.get("is_disposable_email", {}).get("value", False)
    if not is_valid_fmt:
        disp = "❌ Sai định dạng"
    elif is_disposable:
        disp = "🗑️ Email tạm thời"
    elif status_raw == "DELIVERABLE":
        disp = "✅ Hợp lệ"
    elif status_raw == "UNDELIVERABLE":
        disp = "🚫 Không hợp lệ"
    elif status_raw == "RISKY":
        disp = "⚠️ Rủi ro"
    else:
        disp = "❓ Không xác định"
    return {
        "Email": final.get("email", email),
        "Trạng thái": disp,
        "Khả năng gửi (raw)": final.get("deliverability", "-"),
        "Định dạng hợp lệ": "Có" if is_valid_fmt else "Không",
        "MX record": "Có" if final.get("is_mx_found", {}).get("value") else "Không",
        "SMTP hợp lệ": "Có" if final.get("is_smtp_valid", {}).get("value") else "Không",
    }

# ========== GIAO DIỆN STREAMLIT ==========
st.set_page_config(page_title="Kiểm tra Email (Giới hạn concurrency)", layout="wide")
st.title("📧 Kiểm tra Email — Giới hạn xử lý đồng thời để an toàn")

st.markdown("**Tùy chỉnh giới hạn:** thay đổi số luồng / giới hạn SMTP / giới hạn API để cân bằng tốc độ và an toàn.")

col1, col2, col3 = st.columns([1.5,1,1])
with col1:
    workers = st.slider("Số luồng tổng (ThreadPool)", 2, 40, 10)
with col2:
    smtp_concurrency = st.slider("Kết nối SMTP đồng thời", 1, 20, 5)
with col3:
    api_concurrency = st.slider("Request API đồng thời", 1, 20, 5)

api_min_interval_ms = st.slider("Khoảng cách tối thiểu giữa 2 request trên cùng 1 key (ms)", 100, 2000, 500)

emails_input = st.text_area("Nhập danh sách email (mỗi email 1 dòng):", height=220)
start_btn = st.button("🚀 Bắt đầu (Giới hạn an toàn)")

# khởi tạo semaphore & api manager theo cấu hình UI
if start_btn:
    # update global semaphores & api manager
    SMTP_SEMAPHORE = threading.Semaphore(smtp_concurrency)
    API_SEMAPHORE = threading.Semaphore(api_concurrency)
    # recreate api manager with new min interval
    api_key_manager = ApiKeyManager(API_KEYS, min_interval_ms=api_min_interval_ms)

    emails = [e.strip() for e in emails_input.splitlines() if e.strip()]
    if not emails:
        st.warning("Vui lòng nhập ít nhất một email.")
    else:
        total = len(emails)
        progress = st.progress(0)
        status = st.empty()
        results = []
        start_time = time.time()
        # ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as exec:
            futures = {exec.submit(process_email, e): e for e in emails}
            done = 0
            for fut in as_completed(futures):
                e = futures[fut]
                try:
                    res = fut.result()
                except Exception as ex:
                    res = {"Email": e, "Trạng thái": f"⚠️ Lỗi: {ex}"}
                results.append(res)
                done += 1
                progress.progress(done / total)
                status.text(f"Đã xong {done}/{total} — hiện: {e}")
        elapsed = time.time() - start_time
        status.success(f"Hoàn tất {total} email trong {elapsed:.1f}s")
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True)

        # Download CSV/Excel
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Tải CSV", data=csv, file_name="ketqua.csv", mime="text/csv")
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Kết quả")
        st.download_button("📥 Tải Excel", data=output.getvalue(), file_name="ketqua.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
