# ایمپورت کتابخانه‌های مورد نیاز
from flask import Flask, request, jsonify  # فریم‌ورک Flask و ابزارهای API
from flask_cors import CORS                # برای فعال‌سازی CORS جهت اتصال فرانت‌اند
import redis                                # ارتباط با Redis برای کش
import psycopg2                             # اتصال به پایگاه‌داده PostgreSQL
import datetime                             # ثبت زمان‌ها
import os                                   # خواندن متغیرهای محیطی
import jwt                                  # برای رمزگشایی توکن JWT
import logging                              # لاگ‌گیری
import time                                 # ایجاد تأخیر برای اتصال مجدد

# ساخت اپلیکیشن Flask
app = Flask(__name__)
CORS(app)  # فعال‌سازی CORS

# تنظیمات لاگ‌گیری
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

# تنظیمات اتصال Redis با استفاده از متغیرهای محیطی
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, db=0)

# تنظیمات اتصال به PostgreSQL با پشتیبانی از تلاش مجدد
pg_config = {
    "dbname": os.getenv("PG_DB", "namerdb"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASS", "password"),
    "host": os.getenv("PG_HOST", "postgres"),
    "port": os.getenv("PG_PORT", "5432")
}

# تلاش چندباره برای اتصال به پایگاه‌داده (حداکثر 10 بار)
for attempt in range(10):
    try:
        conn = psycopg2.connect(**pg_config)
        cursor = conn.cursor()
        break
    except psycopg2.OperationalError as e:
        logging.warning(f"[{attempt+1}/10] PostgreSQL آماده نیست. تلاش مجدد در 3 ثانیه...")
        time.sleep(3)
else:
    logging.critical("اتصال به PostgreSQL انجام نشد.")
    raise SystemExit()

# ایجاد جدول‌ها در PostgreSQL در صورت نبود
cursor.execute("""
CREATE TABLE IF NOT EXISTS UserRequestLogs (
    id SERIAL PRIMARY KEY,
    ip_address TEXT,
    keyword TEXT,
    count INTEGER,
    timestamp TIMESTAMP,
    user_token TEXT
);

CREATE TABLE IF NOT EXISTS GeneratedNames (
    id SERIAL PRIMARY KEY,
    name TEXT,
    keyword TEXT,
    created_at TIMESTAMP,
    request_id INTEGER REFERENCES UserRequestLogs(id)
);
""")
conn.commit()

# تابع تولید نام‌ها از یک کلیدواژه
def generate_names(keyword, count=5):
    return [
        f"{keyword}ly",
        f"{keyword}ify",
        f"{keyword}Lab",
        f"Go{keyword}",
        f"{keyword}Hub"
    ][:count]

# تابع اختیاری برای دریافت اطلاعات کاربر از JWT
def get_user_from_token():
    auth_header = request.headers.get('Authorization')
    secret_key = os.getenv("SECRET_KEY", "default_secret")
    if not auth_header:
        return None
    try:
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return payload
    except Exception as e:
        logging.error(f"خطای JWT: {e}")
        return None

# مسیر مانیتورینگ برای Prometheus
@app.route('/metrics', methods=['GET'])
def metrics():
    return "name_generator_requests_total 1\n", 200, {'Content-Type': 'text/plain'}

# مسیر اصلی API برای تولید نام‌ها
@app.route('/generate-names', methods=['POST'])
def generate():
    user_info = get_user_from_token()  # دریافت اطلاعات کاربر از JWT (در صورت وجود)

    data = request.json
    keyword = data.get('keyword')
    count = int(data.get('count', 5))

    if not keyword:
        return jsonify({'error': 'Keyword is required'}), 400

    cache_key = f"{keyword}:{count}"
    cached = redis_client.get(cache_key)

    if cached:
        names = cached.decode('utf-8').split(',')
        logging.info(f"داده از کش برای '{keyword}' دریافت شد.")
    else:
        names = generate_names(keyword, count)
        redis_client.setex(cache_key, 3600, ','.join(names))
        logging.info(f"داده در کش برای '{keyword}' ذخیره شد.")

    ip = request.remote_addr
    timestamp = datetime.datetime.utcnow()
    user_token = user_info['sub'] if user_info and 'sub' in user_info else None

    # ذخیره لاگ درخواست در پایگاه‌داده
    cursor.execute("""
        INSERT INTO UserRequestLogs (ip_address, keyword, count, timestamp, user_token)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    """, (ip, keyword, count, timestamp, user_token))
    request_id = cursor.fetchone()[0]

    # ذخیره نام‌های تولیدشده در جدول
    for name in names:
        cursor.execute("""
            INSERT INTO GeneratedNames (name, keyword, created_at, request_id)
            VALUES (%s, %s, %s, %s)
        """, (name, keyword, timestamp, request_id))
    conn.commit()

    logging.info(f"{len(names)} نام برای '{keyword}' از IP {ip} تولید شد.")
    return jsonify({'names': names})

# اجرای برنامه روی پورت ۵۰۰۰
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

