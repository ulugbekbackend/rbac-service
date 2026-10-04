# RBAC Service

Rollar va ruxsatlarni (Role-Based Access Control) boshqarish moduli. Django 5.2 LTS + Django REST Framework, PostgreSQL, Redis.

Imkoniyatlar:

- rollar va permissionlar CRUD, rolga permission biriktirish
- userga rol biriktirish / olib tashlash, userning effektiv permissionlari
- `check-access` va `check-access/bulk` — dostupni tekshirish
- route darajasida permission guard (`require_permission("loans.approve")`), ruxsat bo'lmasa 403
- effektiv permissionlar Redis'da keshlanadi, o'zgarishda kesh tozalanadi
- qo'shimcha: permission override (allow/deny), audit log, super-admin rol
- userlarni boshqarish API (yaratish, ro'yxat, tahrirlash, nofaol qilish) va `/auth/me`
- API dokumentatsiyasi: Swagger (`/api/docs/`) va Postman collection (`postman/`)

## Ishga tushirish

### Docker orqali

```bash
cp .env.example .env        # SECRET_KEY (kamida 50 belgili tasodifiy satr) va ADMIN_PASSWORD ni o'zgartiring
docker compose up --build
```

Konteyner ishga tushganda migratsiyalar, seed (rollar va permissionlar) avtomatik bajariladi va `.env` dagi `ADMIN_USERNAME` / `ADMIN_PASSWORD` bilan `super_admin` rolidagi birinchi user yaratiladi. Shundan keyin hamma ish API orqali qilinadi — `manage.py` buyruqlari kerak emas.

API: http://localhost:8000/api/v1/ , Swagger: http://localhost:8000/api/docs/ , admin panel: http://localhost:8000/admin/

Web konteyner gunicorn bilan ishlaydi, static fayllar (admin panel CSS/JS) whitenoise orqali beriladi.

Agar 5432/6379/8000 portlar band bo'lsa, `.env` da `DB_HOST_PORT`, `REDIS_HOST_PORT`, `WEB_PORT` ni o'zgartirish mumkin.

### Lokal (venv)

PostgreSQL va Redis kerak (`docker compose up -d db redis` bilan ko'tarsa ham bo'ladi).

```bash
python -m venv venv
venv\Scripts\activate          # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python manage.py migrate
python manage.py seed_rbac      # .env dagi ADMIN_USERNAME/ADMIN_PASSWORD bilan admin ham yaratiladi
python manage.py runserver
```

### Tez sinab ko'rish (Swagger orqali)

1. http://localhost:8000/api/docs/ ni oching.
2. `POST /api/v1/auth/token/` — `.env` dagi admin login/paroli bilan token oling.
3. **Authorize** tugmasini bosib, `access` tokenni kiriting.
4. `GET /api/v1/rbac/roles` — rollar va ularning `id`lari.
5. `POST /api/v1/users` — yangi user yarating, masalan `operator` roli bilan:
   `{"username": "ali", "password": "Kuchli-parol-123", "role_ids": [4]}`
6. **Authorize** dan chiqib, `ali` ning tokeni bilan kiring va tekshiring:
   - `GET /api/v1/auth/me` — rollari va permissionlari
   - `POST /api/v1/loans/1/approve` — `403`, operator'da `loans.approve` yo'q
   - `GET /api/v1/rbac/check-access?permission=loans.view` — `has_access: true`
7. Admin bilan `ali` ga `manager` rolini bering (`POST /api/v1/rbac/users/{id}/roles`) — endi `loans/1/approve` `200` qaytaradi (kesh darhol yangilanadi).

### Postman

`postman/RBAC_Service.postman_collection.json` — barcha endpointlar (51 ta so'rov), 8 ta papkada:

| Papka | Ichida |
|---|---|
| 0. Auth | login, refresh, `/auth/me` |
| 1. Permissions | ro'yxat, yaratish, takror/noto'g'ri codename (400), tahrirlash |
| 2. Roles | CRUD, rolga permission biriktirish va olib tashlash |
| 3. Users | user yaratish, zaif parol (400), qidiruv, rollar, effektiv permissionlar |
| 4. Check access | `check-access` va `bulk` |
| 5. Ssenariy: guard va kesh | user 403 oladi → rol berilgach 200 → deny override bilan 403 → rol olinganda yana 403 |
| 6. Xatolar | 401, 409, 404 |
| 7. Tozalash | ssenariyda yaratilganlarni o'chiradi |

Ishlatish:

1. Postman → **Import** → shu faylni tanlang.
2. Collection → **Variables**: `base_url` (default `http://localhost:8000`) va `admin_password` ni `.env` dagi qiymatga moslang.
3. Collection → **Run** — so'rovlar tartib bilan ishlaydi. Token va id'lar avtomatik saqlanadi, har bir so'rovda status kodi va javob tekshiriladi. Collection'ni qayta-qayta ishga tushirsa bo'ladi (har safar yangi nomlar bilan).

Alohida so'rov yuborishdan oldin `0. Auth / Login (admin)` ni bir marta ishga tushiring.

Terminalda ham ishga tushirsa bo'ladi:

```bash
npx newman run postman/RBAC_Service.postman_collection.json --env-var admin_password=<parol>
```

### Testlar

```bash
pytest                                  # lokal venv'da
docker compose exec web pytest          # yoki Docker ichida (Python o'rnatish shart emas)
```

Testlar PostgreSQL'da ishlaydi (test bazasi avtomatik yaratiladi), kesh uchun testda locmem ishlatiladi. Hozir 109 ta test bor:

| Fayl | Nimani tekshiradi |
|---|---|
| `test_roles.py` | rollar CRUD, pagination, 409, rolga permission biriktirish/olib tashlash |
| `test_permissions.py` | permissionlar CRUD, `module` filter, codename formati va takrorlanishi |
| `test_user_roles.py` | userga rol berish/olish, effektiv permissionlar, override, audit log |
| `test_check_access.py` | `check-access` va `bulk`: turli rol kombinatsiyalari, override, super-admin, `users.view_access` |
| `test_guard.py` | himoyalangan endpointga 403/401/200, noto'g'ri va muddati o'tgan token |
| `test_cache.py` | har bir o'zgarishdan keyin kesh tozalanishi |
| `test_seed.py` | seed: standart ma'lumotlar, qayta ishga tushirish, API o'zgarishlarini saqlash, `.env` dagi admin, `--admin` |
| `users/tests/test_users.py` | userlar CRUD, parol tekshiruvi, nofaol qilish, yaratilgan user bilan login, `/auth/me` |

## Autentifikatsiya

JWT (Bearer):

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "..."}'
```

Javobdagi `access` tokenni `Authorization: Bearer <token>` headerida yuboriladi. Yangilash: `POST /api/v1/auth/token/refresh/`. Access token 30 daqiqa, refresh token 7 kun amal qiladi.

Joriy user, uning rollari va effektiv permissionlari: `GET /api/v1/auth/me`.

Swagger'da sinash uchun: token oling, yuqoridagi **Authorize** tugmasini bosib, tokenni kiriting.

## Ma'lumotlar bazasi tuzilishi

Migratsiyalar: `users/migrations/0001_initial.py` va `rbac/migrations/0001_initial.py`.

User modeli — `users/models.py` dagi `User` (Django'ning `AbstractUser` klassidan meros oladi), jadval nomi `users`. Undagi asosiy maydonlar: `username`, `password` (hash), `email`, `first_name`, `last_name`, `is_active`, `date_joined`. Rollar user jadvalida emas, alohida `rbac_userrole` jadvalida saqlanadi.

> Bazada Django'ning o'z jadvallari ham bor: `auth_group`, `auth_permission`, `users_groups`, `users_user_permissions`. Ular faqat Django admin paneli uchun, RBAC moduli ularni ishlatmaydi. RBAC ma'lumotlari faqat `rbac_*` jadvallarida.

| Jadval | Asosiy ustunlar | Izoh |
|---|---|---|
| `users` | `username` (unique), `password`, `email`, `first_name`, `last_name`, `is_active` | Userlar. `is_active=false` bo'lsa login qila olmaydi |
| `rbac_role` | `name` (unique slug), `display_name`, `description`, `is_super_admin` | `name` — kodda ishlatiladigan nom, `display_name` — UI uchun |
| `rbac_permission` | `codename` (unique), `display_name`, `module` (index), `description` | `module` codename'dan avtomatik olinadi (`loans.approve` → `loans`), filter uchun |
| `rbac_rolepermission` | `role_id`, `permission_id`, `created_at` | M2M, `UNIQUE(role, permission)` |
| `rbac_userrole` | `user_id`, `role_id`, `assigned_by_id`, `assigned_at` | M2M, `UNIQUE(user, role)`; kim va qachon biriktirgani saqlanadi. `role` FK `PROTECT` — biriktirilgan rolni bazadan tasodifan o'chirib bo'lmaydi |
| `rbac_userpermission` | `user_id`, `permission_id`, `is_denied`, `granted_by_id` | Override: roldan tashqari ruxsat berish yoki taqiqlash, `UNIQUE(user, permission)` |
| `rbac_auditlog` | `actor_id`, `action`, `target_user_id`, `role_id`, `permission_id`, `created_at` | Rol/override o'zgarishlari tarixi, index `(target_user, created_at)` |

Nega shunday:

- M2M bog'lanishlar alohida through-jadvallar orqali — qo'shimcha ma'lumot (kim, qachon) saqlash mumkin bo'lishi uchun.
- Unique constraintlar dublikatlarni baza darajasida oldini oladi, ular indeks vazifasini ham bajaradi (`user_id` bo'yicha qidiruv tez).
- Audit log'da FK'lar `SET NULL` — rol yoki permission o'chirilsa ham tarix qoladi.

### Codename qoidalari

- Format: `<module>.<action>`, masalan `loans.approve`. Nuqtasiz yoki bo'sh qismli nom (`export`, `loans.`) qabul qilinmaydi.
- Codename saqlashdan oldin bo'shliqlardan tozalanadi va kichik harfga o'tkaziladi: `" Loans.Approve "` → `loans.approve`. Shu sababli `Loans.Approve` va `loans.approve` bitta permission hisoblanadi.
- Takrorlangan codename (har qanday harf ko'rinishida) yuborilsa — `400`, `"Bu codename allaqachon mavjud"`.

### Effektiv permission qanday hisoblanadi

1. Userning barcha rollaridagi permissionlar birlashtiriladi.
2. `user_permission`dagi `is_denied=false` yozuvlar qo'shiladi.
3. `is_denied=true` yozuvlar olib tashlanadi (deny har doim ustun).
4. Userda `is_super_admin=true` bo'lgan rol bo'lsa — har qanday tekshiruv `true`.

## Keshlash

Natija Redis'da `user:{id}:permissions` key ostida saqlanadi, TTL — `PERMISSIONS_CACHE_TTL` (default 900 soniya).

Kesh quyidagi holatlarda tozalanadi (tranzaksiya commit bo'lgandan keyin):

- rolga permission qo'shilganda / olib tashlanganda — shu roldagi barcha userlar
- rol tahrirlanganda (masalan `is_super_admin` o'zgarsa)
- permission tahrirlanganda yoki o'chirilganda — unga rol yoki override orqali ega bo'lgan barcha userlar
- userga rol berilganda / olinganda, override o'zgarganda — shu user

## Rollar va permissionlar (seed)

`python manage.py seed_rbac` — faqat yo'q rol va permissionlarni yaratadi:

- bor yozuvlarga tegmaydi: API orqali o'zgartirilgan nomlar, roldan olib tashlangan permissionlar qayta ishga tushirilganda saqlanib qoladi. Shuning uchun Docker uni har startda xavfsiz ishlatadi;
- o'chirib yuborilgan seed roli permissionlari bilan qayta yaratiladi;
- seed'ga keyinchalik yangi permission qo'shilsa, u yaratiladi, lekin mavjud rollarga avtomatik biriktirilmaydi — buni API orqali qilish kerak;
- `.env` da `ADMIN_USERNAME` va `ADMIN_PASSWORD` berilgan bo'lsa va bunday user hali yo'q bo'lsa — uni `super_admin` roli bilan yaratadi. Bor userga tegmaydi;
- `--admin <username>` — mavjud userga `super_admin` rolini beradi.

| Rol | Permissionlar |
|---|---|
| `super_admin` | barchasi (`is_super_admin`) |
| `admin` | barcha seed permissionlar |
| `manager` | users.view, loans.view, loans.approve, loans.reject, reports.view, reports.export |
| `operator` | users.view, loans.view |
| `viewer` | users.view, loans.view, reports.view |

Permissionlar: `roles.manage`, `permissions.manage`, `users.view_access`, `users.view`, `users.create`, `users.update`, `users.delete`, `loans.view`, `loans.approve`, `loans.reject`, `reports.view`, `reports.export`.

## API

RBAC endpointlari `/api/v1/rbac/` prefiksi ostida. Oxiridagi `/` ixtiyoriy.

### Foydalanuvchilar (`/api/v1/users`)

TZ'da talab qilinmagan, lekin tizimni API orqali to'liq sinash uchun qo'shilgan. Model: `users/models.py`.

| Method | Endpoint | Huquq | Tavsif |
|---|---|---|---|
| GET | `/api/v1/users?search=ali` | `users.view` | Ro'yxat (pagination, username/email bo'yicha qidiruv), har bir user rollari bilan |
| POST | `/api/v1/users` | `users.create` | `{"username", "password", "email", "first_name", "last_name", "role_ids": []}` |
| GET | `/api/v1/users/{id}` | `users.view` | |
| PUT/PATCH | `/api/v1/users/{id}` | `users.update` | `email`, `first_name`, `last_name`, `is_active`, `password`. `username` o'zgarmaydi |
| DELETE | `/api/v1/users/{id}` | `users.delete` | Bazadan o'chirmaydi, `is_active=false` qiladi — audit tarixi saqlanadi, user login qila olmaydi |
| GET | `/api/v1/auth/me` | token | Joriy user, rollari, `is_super_admin`, permissionlari |

- Parol Django'ning standart tekshiruvlaridan o'tadi (kamida 8 belgi, juda oddiy yoki faqat raqamli bo'lmasligi kerak).
- O'zingizni o'chirish yoki nofaol qilish mumkin emas (`400`).
- `role_ids` bilan yaratilganda rol biriktirish audit log'ga yoziladi.

### Rollar (`roles.manage`)

| Method | Endpoint | Tavsif |
|---|---|---|
| GET | `/roles` | Ro'yxat (pagination, `?page=`) |
| POST | `/roles` | Yaratish |
| GET | `/roles/{id}` | Permissionlari bilan |
| PUT/PATCH | `/roles/{id}` | Tahrirlash |
| DELETE | `/roles/{id}` | O'chirish. Userlarga biriktirilgan bo'lsa — `409 conflict` (baza darajasida `PROTECT` bilan, bir vaqtdagi so'rovlarda ham) |
| POST | `/roles/{id}/permissions` | `{"permission_ids": [1, 2]}` |
| DELETE | `/roles/{id}/permissions/{permission_id}` | Bitta permissionni olib tashlash |

### Permissionlar (`permissions.manage`)

| Method | Endpoint | Tavsif |
|---|---|---|
| GET | `/permissions?module=loans` | Ro'yxat, module bo'yicha filter |
| POST | `/permissions` | `{"codename": "loans.approve", "display_name": "..."}`, `module` avtomatik |
| GET / PUT / PATCH / DELETE | `/permissions/{id}` | |

### Userlar

| Method | Endpoint | Huquq |
|---|---|---|
| GET | `/users/{user_id}/roles` | `roles.manage` yoki o'zi |
| POST | `/users/{user_id}/roles` | `roles.manage`, body: `{"role_ids": [1]}` |
| DELETE | `/users/{user_id}/roles/{role_id}` | `roles.manage` |
| GET | `/users/{user_id}/permissions` | `roles.manage` yoki o'zi |
| GET / POST | `/users/{user_id}/permission-overrides` | `roles.manage`, body: `{"permission_id": 5, "is_denied": true}` |
| DELETE | `/users/{user_id}/permission-overrides/{permission_id}` | `roles.manage` |
| GET | `/audit-logs?user_id=` | `roles.manage` |

### Dostupni tekshirish

```http
GET /api/v1/rbac/check-access?permission=loans.approve
GET /api/v1/rbac/check-access?permission=loans.approve&user_id=123
```

```json
{"user_id": 123, "permission": "loans.approve", "has_access": true}
```

```http
POST /api/v1/rbac/check-access/bulk
{"user_id": 123, "permissions": ["loans.approve", "loans.reject", "reports.export"]}
```

```json
{"user_id": 123, "results": {"loans.approve": true, "loans.reject": false, "reports.export": true}}
```

`user_id` berilmasa token egasi tekshiriladi. Boshqa userni tekshirish uchun `users.view_access` kerak.

## Boshqa endpointlarni himoyalash

```python
from rbac.permissions import require_permission


@api_view(["POST"])
@permission_classes([require_permission("loans.approve")])
def approve_loan(request, loan_id):
    ...


class ReportExportView(APIView):
    permission_classes = [require_permission("reports.export")]
```

Misol sifatida `loans` app'ida ikkita endpoint bor: `POST /api/v1/loans/{id}/approve` va `POST /api/v1/loans/{id}/reject`.

Ruxsat bo'lmasa:

```json
HTTP 403
{"error": "forbidden", "message": "Ushbu amal uchun ruxsat yo'q", "required_permission": "loans.approve"}
```

## Xatolar formati

Barcha xatolar bir xil ko'rinishda qaytadi: `{"error": "<kod>", "message": "<matn>"}`.

| HTTP | `error` | Qachon |
|---|---|---|
| 400 | `validation_error` | So'rov ma'lumotlari noto'g'ri. Qaysi maydonda xato borligi `details` ichida |
| 401 | `not_authenticated` | Token yuborilmagan |
| 401 | `token_not_valid` | Token noto'g'ri (`"Token is invalid"`) yoki muddati o'tgan (`"Token is expired"`) |
| 401 | `no_active_account` | Login/parol noto'g'ri yoki user nofaol qilingan |
| 403 | `forbidden` | Ruxsat yo'q, qo'shimcha `required_permission` maydoni bilan |
| 404 | `not_found` | Obyekt topilmadi |
| 409 | `conflict` | Userlarga biriktirilgan rolni o'chirishga urinish |

```json
HTTP 400
{"error": "validation_error", "message": "So'rov ma'lumotlari noto'g'ri",
 "details": {"codename": ["Bu codename allaqachon mavjud"]}}
```

```json
HTTP 401
{"error": "token_not_valid", "message": "Token is expired"}
```

## Loyiha tuzilishi

```
config/      settings, urls, xatolar formati (exception handler)
rbac/        modellar, servis (hisoblash + kesh), API, guard, seed command, testlar
users/       User modeli, userlarni boshqarish API va /auth/me
loans/       guard'ni ko'rsatish uchun demo endpointlar
postman/     Postman collection
```
