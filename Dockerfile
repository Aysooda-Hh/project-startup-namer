FROM python:3.9-slim

# مسیر کاری کانتینر را به پوشه app تنظیم می‌کند
WORKDIR /app

# تمام فایل‌های پروژه را به داخل کانتینر کپی می‌کند
COPY . /app

# نصب وابستگی‌ها از فایل requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# اعلام پورت پیش‌فرض اپلیکیشن
EXPOSE 5000

# اجرای فایل app.py به‌عنوان ورودی اصلی برنامه
CMD ["python", "app.py"]