# RixPanel MVP v1 — Flat Railway Package

همهٔ فایل‌های لازم در سطح ریشهٔ همین پوشه هستند؛ هیچ پوشهٔ داخلی برای import یا اجرای برنامه لازم نیست.

## اجرا

```bash
./run.sh
```

سپس `http://127.0.0.1:8765` را باز کنید.

برای پورت دلخواه:

```bash
PORT=9000 ./run.sh
```

## تست

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
```

## Railway

- Root Directory: خالی یا `.` (ریشهٔ همین پوشه)
- Builder: `RAILPACK`
- Start Command: `python3 app.py --host 0.0.0.0 --port ${PORT:-8765}`
- Healthcheck Path: `/api/health`

## رفتار خودکار

دامنه از آدرس عمومی فعلی پنل خوانده می‌شود. سپس Server، SNI، Host، پورت ۴۴۳، مسیر `/rix-ws` و UUID به‌صورت خودکار ساخته می‌شوند. هیچ فیلد فنی در رابط کاربری لازم نیست.

## فایل‌های اصلی

- `app.py`: اجرای وب‌سرور
- `server.py`: API و فایل‌های استاتیک
- `config_builder.py`: ساخت VLESS/WebSocket، UUID و Subscription
- `index.html`, `app.js`, `styles.css`: رابط فارسی RTL
- `test_*.py`: تست‌های واقعی HTTP و ساخت کانفیگ
