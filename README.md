# Future Scholars Mentorship — Telegram Mini App

Google Sheet'dagi "ish jadvali" asosida qurilgan Telegram bot + mini ilova.
Faqat Python (3.10+) kerak, qo'shimcha kutubxona o'rnatilmaydi.

## Bo'limlar
| Bo'lim | Kim to'ldiradi |
|---|---|
| 📘 Ko'rsatma | — |
| 🎓 Universitetlar (≤10, Reach/Match/Safety, x/10 hisob) | O'quvchi |
| 🏅 Faoliyatlar (turi bo'yicha soat + jami soat avtomatik) | O'quvchi |
| 🗓 Haftalik reja (bajarilgan %, o'rtacha ball avtomatik) | Vazifa, muddat, izoh, ball — mentor; holat, natija, isbot — o'quvchi |
| 📝 Testlar | O'quvchi |
| 👥 O'quvchilar | Faqat admin |

**Maxfiylik:** har bir o'quvchi faqat o'z ma'lumotini ko'radi. Admin (ADMIN_ID) barcha o'quvchilarni ko'radi va tahrirlaydi. Ro'yxatda yo'q odam ilovaga kira olmaydi. Har so'rov Telegram `initData` imzosi bilan tekshiriladi.

## Sozlash
1. `.env` faylini to'ldiring: `BOT_TOKEN`, `ADMIN_ID`, `WEBAPP_URL`.
2. Ishga tushiring:
   ```
   python server.py
   ```
3. Telegram mini ilovasi **HTTPS** manzil talab qiladi. Kompyuterdan sinash uchun:
   ```
   cloudflared tunnel --url http://localhost:8080
   ```
   Bergan `https://....trycloudflare.com` manzilni `.env` dagi `WEBAPP_URL` ga yozing va serverni qayta ishga tushiring.
   Doimiy ishlatish uchun serverni VPS/hostingga joylang.

## O'quvchi qo'shish
- O'quvchi botga `/start` yozadi → bot sizga uning ID sini yuboradi.
- Ilovada «👥 O'quvchilar» → «+ Qo'shish», yoki botda: `/add 123456789 Ism Familiya`
- Boshqa buyruqlar: `/users`, `/remove ID`, `/help`

Ma'lumotlar `data.db` (SQLite) faylida saqlanadi — undan zaxira nusxa oling.
