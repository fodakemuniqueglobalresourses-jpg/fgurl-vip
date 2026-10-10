import os
import sqlite3
import datetime
import qrcode
import bcrypt 
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

if __name__ == "__main__":
    # This reads the port assigned by Render, or defaults to 5000 locally
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

DATABASE_FILE = "database.db"
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024 

def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, job_type TEXT, 
            actual_price REAL, vip_money REAL, total_price REAL, status TEXT, timestamp TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vip_cards (
            card_id TEXT PRIMARY KEY, username TEXT, name TEXT,
            phone TEXT, sex TEXT, tier TEXT, issue_date TEXT, qr_path TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, sender TEXT, 
            message_text TEXT, timestamp TEXT, is_read INTEGER
        )
    """)
    conn.commit()
    conn.close()

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username').strip().lower()
    password = data.get('password')
    if not username or not password:
        return jsonify({"message": "Inputs cannot be left empty."}), 400
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"message": "Error: That username is already registered under FGURL VIP."}), 400
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
    conn.commit()
    conn.close()
    return jsonify({"message": "FGURL VIP Profile Formed Successfully!"}), 200

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username').strip().lower()
    password = data.get('password')
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode('utf-8'), row.encode('utf-8')):
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("logins.txt", "a") as log_file:
            log_file.write(f"[{current_time}] AUTH SUCCESS - Profile '{username}' entered the FGURL VIP Portal.\n")
        return jsonify({"message": "Access Verified! Loading panel..."}), 200
    return jsonify({"message": "Error: Invalid entry credentials. Access Denied."}), 401

@app.route('/api/check-expiry', methods=['GET'])
def check_expiry():
    username = request.args.get('user').strip().lower()
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT tier, issue_date FROM vip_cards WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if not row: return jsonify({"status": "active", "has_card": False}), 200
    return jsonify({"status": "active", "has_card": True}), 200

@app.route('/api/create-vip', methods=['POST'])
def create_vip():
    username = request.form.get('username').strip().lower()
    name = request.form.get('name')
    phone = request.form.get('phone')
    sex = request.form.get('sex')
    tier = request.form.get('tier')
    issue_date = request.form.get('issue_date')
    
    passport = request.files.get('passport')
    if passport:
        os.makedirs("uploads", exist_ok=True)
        unique_suffix = int(time.time())
        file_extension = os.path.splitext(passport.filename) or '.jpg'
        passport_name = f"{username}_{unique_suffix}_passport{file_extension}"
        passport.save(os.path.join("uploads", passport_name))

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vip_cards")
    count = cursor.fetchone() + 1
    card_sequence_number = f"{count:03d}" 

    qr_data = f"FGURL VIP CARD ID: {card_sequence_number}\nHolder: {name}\nContact: {phone}\nGender: {sex}\nPlan: {tier}"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white")
    os.makedirs("uploads", exist_ok=True)
    qr_filename = f"uploads/{card_sequence_number}_qr.png"
    qr_img.save(qr_filename)

    cursor.execute("DELETE FROM vip_cards WHERE username = ?", (username,))
    cursor.execute("""
        INSERT INTO vip_cards (card_id, username, name, phone, sex, tier, issue_date, qr_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (card_sequence_number, username, name, phone, sex, tier, issue_date, qr_filename))
    conn.commit()
    conn.close()
    return jsonify({"message": f"Successfully mapped FGURL VIP Card #{card_sequence_number}"}), 200

@app.route('/api/checkout-live', methods=['POST'])
def checkout_live():
    data = request.get_json()
    username = data.get('user')
    job_type = data.get('job_type')
    actual_price = float(data.get('actual_price'))
    paystack_ref = data.get('paystack_ref')

    # Security Verification: Confirms directly with Paystack cloud that money landed safely
    paystack_verification_url = f"https://paystack.co{paystack_ref}"
    headers = {
        # ⚠️ PASTE YOUR RECENTLY ACTIVATED LIVE SECRET KEY HERE WHEN DEPLOYED ONLINE
        "Authorization": "Bearer sk_test_your_copied_secret_key_here" 
    }
    
    try:
        response = requests.get(paystack_verification_url, headers=headers).json()
    except Exception:
        return jsonify({"message": "Error verification network connection dropout."}), 500

    if response.get('status') and response['data']['status'] == 'success':
        vip_money = actual_price * 0.25
        total_price = actual_price + vip_money
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 💸 REVENUE DIVISION SPLITS (₦2,200 to Partner / ₦300 to You via your Subaccount)
        partner_share = 2200.00
        your_share = 300.00

        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (username, job_type, actual_price, vip_money, total_price, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, job_type, actual_price, vip_money, total_price, "Payment Confirmed / Approved for Production", timestamp))
        conn.commit()
        conn.close()

        # Cloud console payout log reporting format
        print("\n💰 --- FGURL VIP REAL-TIME CHECKOUT SPLIT COMPILATION ---")
        print(f"Ref Token: [{paystack_ref}] | Account Profile: [{username}]")
        print(f"Total Confirmed Revenue Received: ₦{total_price:,.2f}")
        print(f"-> Automated Payout Sent to Partner Node: ₦{partner_share:,.2f}")
        print(f"-> Your Dedicated Premium Payout (Oladele): ₦{your_share:,.2f} to 8065867966")
        print("-------------------------------------------------------------\n")
        return jsonify({"message": f"Real-time Payment Verified! Total Processed: ₦{total_price:,.2f}."}), 200
    else:
        return jsonify({"message": "Verification parameters fraudulent or invalid."}), 400

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    username = request.args.get('user')
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, job_type, total_price, status, timestamp FROM transactions WHERE username = ? ORDER BY id DESC", (username,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in rows])

if __name__ == '__main__':
    init_db()
    # Runs globally on Render network channels
    app.run(host='0.0.0.0', port=5000, debug=True)
