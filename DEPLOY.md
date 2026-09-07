# คู่มือ Deploy — Content OS

ทำตามลำดับ 3 ส่วน: **Supabase → Meta app → Railway**
ค่าที่ต้องคัดลอกไว้ ให้จดใส่ไฟล์ชั่วคราวก่อน แล้วค่อยเอาไปใส่ Railway ทีเดียว

---

## 1. Supabase (ฐานข้อมูล + ล็อกอิน + เก็บไฟล์)

1. ไปที่ https://supabase.com → **New project** (เลือก region สิงคโปร์ `ap-southeast-1`)
   ตั้งรหัส database password → จดไว้
2. เมนู **Project Settings → Database → Connection string → "Transaction pooler"**
   - คัดลอก URI มา แล้วแก้ 2 จุด:
     - เปลี่ยน `postgresql://` เป็น `postgresql+psycopg://`
     - ต่อท้าย `?sslmode=require`
   - นี่คือ `DATABASE_URL`
3. เมนู **Project Settings → API**:
   - `Project URL` → `SUPABASE_URL`
   - `anon public` key → `SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY`
   - **Project Settings → API → JWT Settings → JWT Secret** → `SUPABASE_JWT_SECRET`
4. เมนู **Authentication → Providers**:
   - เปิด **Email** (เปิด "Confirm email" ไว้ก็ได้)
   - เปิด **Google** — ต้องมี Google OAuth Client ID/Secret
     (สร้างที่ https://console.cloud.google.com → APIs & Services → Credentials →
     OAuth client ID → Web application; ใส่ Authorized redirect URI เป็น
     `https://<project-ref>.supabase.co/auth/v1/callback`)
5. เมนู **Authentication → URL Configuration**:
   - **Site URL** = `https://<ชื่อแอปที่จะได้จาก Railway>` (กลับมาใส่ทีหลังได้)
   - **Redirect URLs** เพิ่ม: `https://<ชื่อแอป>/dashboard` และ
     `http://localhost:8000/dashboard`
6. เมนู **Storage → New bucket** ชื่อ `generated` → ติ๊ก **Public bucket**

---

## 2. Meta app (สำหรับเชื่อม Facebook Page)

1. https://developers.facebook.com/apps → **Create app** → ประเภท **"Business"**
2. ในแอป → **Add product → Facebook Login → Set up**
3. **Facebook Login → Settings**:
   - **Valid OAuth Redirect URIs** = `https://<ชื่อแอป>/connect/facebook/callback`
   - (ตอนเทสต์ในเครื่องเพิ่ม `http://localhost:8000/connect/facebook/callback` ด้วย)
4. **App settings → Basic**:
   - `App ID` → `FACEBOOK_APP_ID`
   - `App Secret` → `FACEBOOK_APP_SECRET`
   - ใส่ **Privacy Policy URL** = `https://<ชื่อแอป>/privacy` (จะทำหน้านี้ทีหลัง)
5. **App roles → Roles** → add ตัวเอง + คนที่จะให้ทดสอบ เป็น **Tester/Developer**
   > ⚠️ ก่อนผ่าน **App Review** ของ Meta จะเชื่อม Page ได้เฉพาะคนที่เป็น
   > admin/developer/tester ในแอปนี้เท่านั้น การเปิดให้คนทั่วไปใช้ต้องยื่น
   > App Review + Business Verification (ทำภายหลัง — ดู Phase 6 ในแผน)
6. permissions ที่โค้ดขอ: `pages_show_list`, `pages_read_engagement`,
   `pages_manage_posts` (ตั้งค่าไว้ใน `FACEBOOK_SCOPES` แล้ว)

---

## 3. Railway (รันแอป)

1. https://railway.app → **New Project → Deploy from GitHub repo** →
   เลือก `sarunporn-ui/auto-post-facebook`
   (Railway จะเจอ `Dockerfile` เอง)
2. เมื่อ deploy รอบแรกเสร็จ → **Settings → Networking → Generate Domain**
   จะได้ URL เช่น `https://auto-post-facebook-production.up.railway.app`
   → นี่คือ `<ชื่อแอป>` เอาไปเติมย้อนกลับใน Supabase ข้อ 5 และ Meta ข้อ 3–4
3. **Variables** → ใส่ทั้งหมดนี้:

   | ตัวแปร | ค่า |
   |---|---|
   | `DATABASE_URL` | จาก Supabase 1.2 |
   | `SUPABASE_URL` | จาก Supabase 1.3 |
   | `SUPABASE_ANON_KEY` | จาก Supabase 1.3 |
   | `SUPABASE_SERVICE_ROLE_KEY` | จาก Supabase 1.3 |
   | `SUPABASE_JWT_SECRET` | จาก Supabase 1.3 |
   | `SUPABASE_STORAGE_BUCKET` | `generated` |
   | `FACEBOOK_APP_ID` | จาก Meta 2.4 |
   | `FACEBOOK_APP_SECRET` | จาก Meta 2.4 |
   | `FACEBOOK_GRAPH_API_VERSION` | `v21.0` |
   | `FACEBOOK_REDIRECT_URI` | `https://<ชื่อแอป>/connect/facebook/callback` |
   | `FACEBOOK_SCOPES` | `pages_show_list,pages_read_engagement,pages_manage_posts` |
   | `FERNET_KEY` | รันคำสั่งข้างล่าง |
   | `INTERNAL_CRON_SECRET` | สุ่มข้อความยาว ๆ |
   | `APPROVAL_WEBHOOK_SECRET` | สุ่มข้อความยาว ๆ |
   | `OPENAI_API_KEY` | key เดิม |
   | `ANTHROPIC_API_KEY` | key เดิม |
   | `LLM_PROVIDER` | `openai` |
   | `LLM_MODEL` | `gpt-5.5` |
   | `APP_BASE_URL` | `https://<ชื่อแอป>` |

   สร้าง `FERNET_KEY`:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   > ⚠️ อย่าเปลี่ยน `FERNET_KEY` หลังมีคนเชื่อม Page แล้ว — token เก่าจะถอดรหัสไม่ได้

4. หลังใส่ variables ครบ → Railway redeploy อัตโนมัติ → เปิด `https://<ชื่อแอป>/dashboard`

---

## ตรวจว่าใช้งานได้

1. เปิด `/dashboard` → ต้องเจอหน้า **Sign in** → ลองอีเมล magic link + Google
2. ล็อกอินเข้ามา → การ์ด **Facebook Page** → กด **Connect Facebook** →
   อนุญาต → เลือก Page → การ์ดขึ้นชื่อ Page
3. วางลิงก์ YouTube → **Generate Ideas** → เลือกหัวข้อ + ฟอร์แมต 2 → **Generate**
4. คอลัมน์ **Publish** → ตั้งเวลา 2 นาทีข้างหน้า → รอ → โพสต์ขึ้น Page จริง
5. ลองสมัครอีกบัญชี → ต้องไม่เห็นคอนเทนต์ของบัญชีแรก (ทดสอบ tenancy)
