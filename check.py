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

# ========== CÀI ĐẶT CỐ ĐỊNH (KHÔNG CHO NGƯỜI DÙNG THAY ĐỔI) ==========
WORKERS = 10                 # số luồng tổng xử lý
SMTP_CONCURRENCY = 5         # số kết nối SMTP đồng thời tối đa
API_CONCURRENCY = 5          # số request API đồng thời tối đa
API_MIN_INTERVAL_MS = 500    # ms: khoảng tối thiểu giữa 2 request trên cùng 1 API key

API_URL = "https://emailvalidation.abstractapi.com/v1/"

# Các danh sách domain/tài khoản vai trò
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

# ========== Quản lý API key với rate-limit per key ==========
class ApiKeyManager:
    def __init__(self, keys, min_interval_ms=500):
        self.keys = list(keys)
        self.min_interval_ms = min_interval_ms
        self.lock = threading.Lock()
        self.last_used = {k: 0.0 for k in self.keys}
        self.index = 0

    def get_key(self, timeout=5.0):
        """Trả về key sẵn sàng dùng trong timeout (hoặc None)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                if not self.keys:
                    return None
                # thử từng key tuần tự
                for _ in range(len(self.keys)):
                    key = self.keys[self.index % len(self.keys)]
                    self.index += 1
                    last = self.last_used.get(key, 0.0)
                    elapsed_ms = (time.time() - last) * 1000.0
                    if elapsed_ms >= self.min_interval_ms:
                        self.last_used[key] = time.time()
                        return key
            time.sleep(0.05)
        return None

_api_manager = ApiKeyManager(API_KEYS, min_interval_ms=API_MIN_INTERVAL_MS)

# Semaphores cố định (khi chạy sẽ dùng chúng)
SMTP_SEMAPHORE = threading.Semaphore(SMTP_CONCURRENCY)
API_SEMAPHORE = threading.Semaphore(API_CONCURRENCY)

# ========== HỖ TRỢ REQUESTS ==========
def requests_get(session, url, **kwargs):
    try:
        r = session.get(url, **kwargs)
        r.raise_for_status()
        return r
    except Exception:
        return None

# ========== GỌI ABSTRACT API (XOAY KEY, Hạn chế concurrency bằng API_SEMAPHORE) ==========
def check_email_api(email, session=None):
    if session is None:
        session = requests.Session()

    acquired = False
    try:
        acquired = API_SEMAPHORE.acquire(timeout=10)
    except Exception:
        acquired = False

    try:
        key = _api_manager.get_key(timeout=10.0)
        if not key:
            return None
        params = {"api_key": key, "email": email}
        try:
            r = session.get(API_URL, params=params, timeout=12)
            if r is None:
                return None
            if r.status_code == 200:
                return r.json()
            return None
        except Exception:
            return None
    finally:
        if acquired:
            API_SEMAPHORE.release()

# ========== LẤY MX RECORD (dùng dnspython nếu có; fallback Google DNS HTTP) ==========
def get_mx_records_robust(domain, session=None):
    if session is None:
        session = requests.Session()
    try:
        # thử dnspython nếu môi trường có
        import dns.resolver
        try:
            answers = dns.resolver.resolve(domain, "MX")
            mx = sorted([(r.preference, r.exchange.to_text()) for r in answers])
            return mx
        except Exception:
            pass
    except Exception:
        # dnspython không có hoặc lỗi -> fallback HTTP
        pass

    # Fallback: Google DNS-over-HTTPS
    try:
        url = f"https://dns.google/resolve?name={domain}&type=MX"
        r = requests_get(session, url, timeout=5)
        if r is None:
            return []
        data = r.json()
        answers = []
        for ans in data.get("Answer", []):
            if ans.get("type") == 15:
                parts = ans["data"].split()
                if len(parts) >= 2:
                    pref = int(parts[0]); exch = parts[1]
                    answers.append((pref, exch.rstrip(".")))
        answers.sort(key=lambda x: x[0])
        return answers
    except Exception:
        return []

# ========== FREE CHECK (Regex + MX + SMTP) ==========
def check_email_free_super_advanced(email, session=None):
    if session is None:
        session = requests.Session()

    result = {
        "email": email,
        "deliverability": "UNKNOWN",
        "quality_score": "-",
        "is_valid_format": {"value": False, "text": "FALSE"},
        "is_free_email": {"value": False, "text": "FALSE"},
        "is_disposable_email": {"value": False, "text": "FALSE"},
        "is_role_email": {"value": False, "text": "FALSE"},
        "is_catchall_email": {"value": False, "text": "UNKNOWN"},
        "is_mx_found": {"value": False, "text": "FALSE"},
        "is_smtp_valid": {"value": False, "text": "UNKNOWN"},
    }

    # 1) Regex
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_valid_format"] = {"value": True, "text": "TRUE"}

    local, domain = email.split("@", 1)
    domain = domain.lower()
    if domain in FREE_DOMAINS:
        result["is_free_email"] = {"value": True, "text": "TRUE"}
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable_email"] = {"value": True, "text": "TRUE"}
        result["deliverability"] = "UNDELIVERABLE"
        return result
    if local.lower() in ROLE_ACCOUNTS:
        result["is_role_email"] = {"value": True, "text": "TRUE"}

    # 2) MX lookup
    mx_records = get_mx_records_robust(domain, session=session)
    if not mx_records:
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_mx_found"] = {"value": True, "text": "TRUE"}

    # 3) Nếu domain miễn phí (Gmail...) -> skip SMTP (thường chặn)
    if result["is_free_email"]["value"]:
        result["deliverability"] = "DELIVERABLE"
        result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
        return result

    # 4) SMTP check (cố định concurrency bằng SMTP_SEMAPHORE)
    for _, mx in mx_records:
        mx_host = mx.rstrip(".")
        acquired = False
        try:
            acquired = SMTP_SEMAPHORE.acquire(timeout=20)
        except Exception:
            acquired = False
        if not acquired:
            # không lấy được semaphore trong timeout -> continue next mx
            continue
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
                        # catch-all test
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
                        # mark risky to force API re-check later
                        result["deliverability"] = "RISKY"
                        result["is_smtp_valid"]["text"] = "SMTP_REJECTION"
                        return result
                    else:
                        result["deliverability"] = "RISKY"
                        continue
            except Exception:
                continue
        finally:
            if acquired:
                SMTP_SEMAPHORE.release()

    return result

# ========== Worker: xử lý 1 email ==========
def process_email_worker(email):
    session = requests.Session()
    try:
        free_res = check_email_free_super_advanced(email, session=session)
    except Exception:
        free_res = {"email": email, "deliverability": "UNKNOWN", "is_valid_format": {"value": False}, "is_free_email": {"value": False}}

    need_api = False
    if free_res.get("deliverability") in ["UNKNOWN", "RISKY"]:
        need_api = True
    if free_res.get("is_free_email", {}).get("value", False):
        need_api = True

    final = free_res
    if need_api:
        api_res = check_email_api(email, session=session)
        if api_res:
            final = api_res

    # map to human-friendly status
    status_raw = (final.get("deliverability") or "").upper()
    is_valid_fmt = final.get("is_valid_format", {}).get("value", False)
    is_disposable = final.get("is_disposable_email", {}).get("value", False)

    if not is_valid_fmt:
        display_status = "❌ Sai định dạng"
    elif is_disposable:
        display_status = "🗑️ Email tạm thời"
    elif status_raw == "DELIVERABLE":
        display_status = "✅ Hợp lệ"
    elif status_raw == "UNDELIVERABLE":
        display_status = "🚫 Không hợp lệ"
    elif status_raw == "RISKY":
        display_status = "⚠️ Rủi ro (Cần API)"
    else:
        display_status = "❓ Không xác định"

    return {
        "Email": final.get("email", email),
        "Trạng thái": display_status,
        "Khả năng gửi (raw)": final.get("deliverability", "-"),
        "Điểm tin cậy": final.get("quality_score", "-"),
        "Định dạng hợp lệ": "Có" if is_valid_fmt else "Không",
        "Loại email": (
            "Miễn phí" if final.get("is_free_email", {}).get("value") else
            "Tạm thời" if final.get("is_disposable_email", {}).get("value") else
            "Chung" if final.get("is_role_email", {}).get("value") else
            "Bình thường"
        ),
        "Catch-all": "Có" if final.get("is_catchall_email", {}).get("value") else "Không",
        "MX record": "Có" if final.get("is_mx_found", {}).get("value") else "Không",
        "SMTP hợp lệ": "Có" if final.get("is_smtp_valid", {}).get("value") else "Không",
    }

# ========== UI Streamlit (tabs: Upload / Manual) ==========
st.set_page_config(page_title="Kiểm tra Email (Cố định concurrency)", layout="wide")
st.title("📧 Kiểm tra Email hàng loạt — Giới hạn cố định (an toàn)")

tab1, tab2 = st.tabs(["📁 Tải file (Excel/CSV)", "✍️ Nhập thủ công"])

with tab1:
    st.header("1) Tải file Excel (.xlsx) hoặc CSV")
    uploaded_file = st.file_uploader("Chọn file (.xlsx hoặc .csv)", type=["xlsx", "csv"])
    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file) if uploaded_file.name.lower().endswith("xlsx") else pd.read_csv(uploaded_file)
            st.info(f"Đã tải lên: **{uploaded_file.name}** — {len(df)} dòng")
            st.dataframe(df.head(10), use_container_width=True)
            st.subheader("Chọn cột chứa Email")
            email_col = st.selectbox("Cột email:", df.columns.tolist())
            if st.button("🚀 Bắt đầu kiểm tra file"):
                emails = []
                rows = []
                for idx, row in df.iterrows():
                    val = row[email_col]
                    if pd.isna(val):
                        emails.append(None)
                    else:
                        # nếu cell chứa nhiều email, lấy cái đầu tiên
                        if isinstance(val, str):
                            e = re.split(r"[,\s;]+", val.strip())[0]
                            emails.append(e.lower())
                        else:
                            emails.append(str(val).lower())
                total = len(emails)
                progress = st.progress(0)
                status = st.empty()
                results = []
                start = time.time()
                with ThreadPoolExecutor(max_workers=WORKERS) as executor:
                    futures = {executor.submit(process_email_worker, e if e else ""): i for i, e in enumerate(emails)}
                    done = 0
                    # preserve order by writing into results_list with index
                    results_list = [None] * total
                    for fut in as_completed(futures):
                        idx = futures[fut]
                        e = emails[idx] if emails[idx] else ""
                        try:
                            res = fut.result()
                        except Exception as ex:
                            res = {"Email": e, "Trạng thái": f"⚠️ Lỗi: {ex}"}
                        results_list[idx] = res
                        done += 1
                        progress.progress(done / total)
                        status.text(f"Đã xử lý {done}/{total}")
                elapsed = time.time() - start
                status.success(f"Hoàn tất {total} dòng trong {elapsed:.1f}s")
                # gắn kết quả vào DataFrame
                df_result = df.copy()
                df_result["KQ_XácThực"] = [r["Trạng thái"] for r in results_list]
                st.subheader("Kết quả (xem trước 10 dòng)")
                st.dataframe(df_result.head(10), use_container_width=True)
                # download file
                csv = df_result.to_csv(index=False).encode("utf-8")
                st.download_button("📥 Tải CSV kết quả", data=csv, file_name=f"ket_qua_{uploaded_file.name.split('.')[0]}.csv", mime="text/csv")
                output = BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df_result.to_excel(writer, index=False, sheet_name="Kết quả")
                st.download_button("📥 Tải Excel kết quả", data=output.getvalue(), file_name=f"ket_qua_{uploaded_file.name.split('.')[0]}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.error(f"Đọc file lỗi: {e}")

with tab2:
    st.header("Nhập danh sách email (mỗi dòng 1 email)")
    emails_input = st.text_area("Danh sách email:", height=220, placeholder="example@gmail.com\nsupport@company.com\n...")
    if st.button("🚀 Bắt đầu kiểm tra (nhập tay)"):
        emails = [e.strip().lower() for e in emails_input.splitlines() if e.strip()]
        if not emails:
            st.warning("Vui lòng nhập ít nhất một email.")
        else:
            total = len(emails)
            progress = st.progress(0)
            status = st.empty()
            results = []
            start = time.time()
            with ThreadPoolExecutor(max_workers=WORKERS) as executor:
                futures = {executor.submit(process_email_worker, e): i for i, e in enumerate(emails)}
                done = 0
                results_list = [None] * total
                for fut in as_completed(futures):
                    idx = futures[fut]
                    e = emails[idx]
                    try:
                        res = fut.result()
                    except Exception as ex:
                        res = {"Email": e, "Trạng thái": f"⚠️ Lỗi: {ex}"}
                    results_list[idx] = res
                    done += 1
                    progress.progress(done / total)
                    status.text(f"Đã xử lý {done}/{total}")
            elapsed = time.time() - start
            status.success(f"Hoàn tất {total} email trong {elapsed:.1f}s")
            df_out = pd.DataFrame(results_list)
            st.dataframe(df_out, use_container_width=True)
            csv = df_out.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Tải CSV kết quả", data=csv, file_name="ket_qua_emails.csv", mime="text/csv")
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_out.to_excel(writer, index=False, sheet_name="Kết quả")
            st.download_button("📥 Tải Excel kết quả", data=output.getvalue(), file_name="ket_qua_emails.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
