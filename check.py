import tkinter as tk
from tkinter import ttk, messagebox
import requests
import threading

API_KEYS = ["c985842edb6f4049a6d0977928cdc4a7"]
current_key_index = 0

def get_next_api_key():
    global current_key_index
    key = API_KEYS[current_key_index]
    current_key_index = (current_key_index + 1) % len(API_KEYS)
    return key

def format_bool(val, yes="Có", no="Không", unknown="-"):
    if val is True:
        return yes
    elif val is False:
        return no
    else:
        return unknown

def build_email_type(is_free, is_temp, is_role):
    types = []
    if is_free: types.append("Miễn phí")
    if is_temp: types.append("Tạm thời")
    if is_role: types.append("Chung")
    return ", ".join(types) if types else "Bình thường"

def translate_deliverability(val):
    if val == "DELIVERABLE":
        return "Gửi được"
    elif val == "UNDELIVERABLE":
        return "Không gửi được"
    elif val == "RISKY":
        return "Rủi ro"
    else:
        return "Không xác định"

def verify_email(email):
    api_key = get_next_api_key()
    url = f"https://emailvalidation.abstractapi.com/v1/?api_key={api_key}&email={email}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return {
                "email": data.get("email"),
                "autocorrect": data.get("autocorrect", ""),
                "deliverability": translate_deliverability(data.get("deliverability")),
                "quality_score": data.get("quality_score"),
                "is_valid_format": data.get("is_valid_format", {}).get("value"),
                "email_type": build_email_type(
                    data.get("is_free_email", {}).get("value"),
                    data.get("is_disposable_email", {}).get("value"),
                    data.get("is_role_email", {}).get("value")
                ),
                "is_catchall_email": data.get("is_catchall_email", {}).get("value"),
                "is_mx_found": data.get("is_mx_found", {}).get("value"),
                "is_smtp_valid": data.get("is_smtp_valid", {}).get("value"),
            }
        else:
            return {"email": email, "deliverability": "Lỗi API"}
    except Exception as e:
        return {"email": email, "deliverability": f"Thất bại ({e})"}

def check_emails():
    email_list = txt_input.get("1.0", tk.END).strip().splitlines()
    if not email_list:
        messagebox.showwarning("Cảnh báo", "Vui lòng nhập ít nhất một email.")
        return

    lbl_loading.config(text="⏳ Đang kiểm tra, vui lòng đợi...")
    btn_check.config(state="disabled")

    def worker():
        for row in tree.get_children():
            tree.delete(row)

        for email in email_list:
            result = verify_email(email.strip())
            tree.insert("", tk.END, values=(
                result.get("email", "-"),
                result.get("autocorrect", ""),
                result.get("deliverability", "-"),
                result.get("quality_score", "-"),
                format_bool(result.get("is_valid_format"), "Đúng", "Sai"),
                result.get("email_type", "Bình thường"),
                format_bool(result.get("is_catchall_email"), "Có", "Không"),
                format_bool(result.get("is_mx_found"), "Có", "Không"),
                format_bool(result.get("is_smtp_valid"), "Có", "Không")
            ))

        lbl_loading.config(text="")
        btn_check.config(state="normal")

    threading.Thread(target=worker).start()

root = tk.Tk()
root.title("Công cụ kiểm tra Email")
root.geometry("1150x600")

lbl = tk.Label(root, text="Nhập danh sách email (mỗi dòng 1 email):", font=("Arial", 11))
lbl.pack(anchor="w", padx=10, pady=5)

txt_input = tk.Text(root, height=6, font=("Arial", 11))
txt_input.pack(fill="x", padx=10, pady=5)

btn_check = tk.Button(root, text="Kiểm tra email", command=check_emails,
                      bg="#4CAF50", fg="white", font=("Arial", 11, "bold"))
btn_check.pack(pady=5)

lbl_loading = tk.Label(root, text="", font=("Arial", 11), fg="blue")
lbl_loading.pack(pady=5)

columns = (
    "Địa chỉ email", "Gợi ý sửa lỗi", "Khả năng gửi", "Điểm tin cậy",
    "Đúng định dạng", "Loại email", "Nhận tất cả", "Có máy chủ email", "Tồn tại thật"
)
tree = ttk.Treeview(root, columns=columns, show="headings")

for col in columns:
    tree.heading(col, text=col)
    tree.column(col, width=120, anchor="center")

tree.column("Địa chỉ email", width=220, anchor="w")
tree.column("Gợi ý sửa lỗi", width=160, anchor="w")
tree.column("Loại email", width=180, anchor="w")

tree.pack(fill="both", expand=True, padx=10, pady=10)

root.mainloop()
