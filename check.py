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
        result["deliverability"] = "UNDELIVERABLE"
        return result
    if local_part.lower() in ROLE_ACCOUNTS:
        result["is_role_email"] = {"value": True, "text": "TRUE"}

    # 3. Kiểm tra MX record bằng Google DNS API
    mx_records = get_mx_records(domain)
    if not mx_records:
        result["deliverability"] = "UNDELIVERABLE"
        return result
    result["is_mx_found"] = {"value": True, "text": "TRUE"}
    mx_record = mx_records[0].split()[-1]  # lấy hostname

    # 4. Kiểm tra SMTP (chỉ với email domain riêng, không phải Gmail/Outlook)
    if result["is_free_email"]["value"]:
        return result

    try:
        import socket
        server = smtplib.SMTP(mx_record, timeout=10)
        server.set_debuglevel(0)
        server.ehlo()
        server.mail('test@example.com')
        code, message = server.rcpt(email)
        server.quit()

        if code == 250:
            result["is_smtp_valid"] = {"value": True, "text": "TRUE"}
            result["deliverability"] = "DELIVERABLE"
        elif code == 550:
            result["is_smtp_valid"] = {"value": False, "text": "FALSE"}
            result["deliverability"] = "UNDELIVERABLE"
        else:
            result["deliverability"] = "RISKY"

    except Exception:
        result["deliverability"] = "UNKNOWN"

    return result