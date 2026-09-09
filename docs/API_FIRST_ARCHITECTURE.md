# البنية المعمارية API-First | API-First Architecture

> **مبدأ أساسي:** CogniForge هو نظام API-First بنسبة 100%

---

## 🎯 ما هو API-First؟ | What is API-First?

**API-First** يعني أن النظام مصمم أولاً وبشكل أساسي كـ API، والواجهة الأمامية (Frontend) اختيارية وقابلة للفصل.

### المبادئ الأساسية | Core Principles

1. **Independence | الاستقلالية**
   - API يعمل بشكل مستقل تماماً عن UI
   - يمكن استخدام API من أي client (Web, Mobile, CLI, etc.)
   - لا توجد تبعية على Frontend

2. **Separation of Concerns | فصل المسؤوليات**
   - API Core لا يعرف شيئاً عن UI/Frontend
   - Static file serving منفصل في middleware اختياري
   - Business logic في Services، ليس في API layer

3. **Flexibility | المرونة**
   - يمكن تشغيل النظام في API-only mode
   - يمكن إضافة أي frontend (React, Vue, Mobile, etc.)
   - سهولة التكامل مع أنظمة خارجية

---

## 🏗️ البنية المعمارية | Architecture

### طبقات النظام | System Layers

```
┌─────────────────────────────────────────┐
│     Frontend (Optional)                 │  ← SPA, Mobile, Desktop
│     app/static/ + middleware            │
└─────────────────────────────────────────┘
              ↓ HTTP/REST
┌─────────────────────────────────────────┐
│     API Layer (Presentation)            │  ← FastAPI Routers
│     app/api/routers/                    │     - admin.py
│                                         │     - crud.py
│                                         │     - security.py
│                                         │     - observability.py
└─────────────────────────────────────────┘
              ↓ Dependencies
┌─────────────────────────────────────────┐
│     Boundary Services (Facade)          │  ← Interface Layer
│     app/services/boundaries/            │     - admin_chat_boundary_service.py
│                                         │     - auth_boundary_service.py
│                                         │     - crud_boundary_service.py
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│     Business Services (Logic)           │  ← Domain Logic
│     app/services/                       │     - admin/
│                                         │     - chat/
│                                         │     - overmind/
│                                         │     - users/
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│     Infrastructure (Data)               │  ← Database, External APIs
│     app/core/, app/infrastructure/      │
└─────────────────────────────────────────┘
```

### المسؤوليات | Responsibilities

#### 1. API Layer (`app/api/routers/`)
- **المسؤولية الوحيدة:** استقبال HTTP requests وإرجاع responses
- **ممنوع:**
  - Business logic
  - Database queries مباشرة
  - معالجة معقدة للبيانات
- **مسموح:**
  - Request validation (Pydantic schemas)
  - Response formatting
  - Dependency injection
  - Error handling

**مثال صحيح:**
```python
@router.post("/login")
async def login(
    login_data: LoginRequest,
    service: AuthBoundaryService = Depends(get_auth_service),
) -> AuthResponse:
    """تسجيل الدخول - API endpoint فقط."""
    result = await service.authenticate_user(
        email=login_data.email,
        password=login_data.password,
    )
    return AuthResponse.model_validate(result)
```

**مثال خاطئ:**
```python
@router.post("/login")
async def login(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    # ❌ خطأ: Business logic في API layer
    user = await db.execute(select(User).where(User.email == login_data.email))
    if not user or not verify_password(login_data.password, user.password):
        raise HTTPException(401)
    token = create_jwt_token(user.id)
    return AuthResponse(token=token)
```

#### 2. Boundary Services (`app/services/boundaries/`)
- **المسؤولية:** Facade pattern - واجهة موحدة للـ API
- **المهام:**
  - تنسيق استدعاءات متعددة للخدمات
  - تحويل البيانات بين API و Services
  - معالجة الأخطاء وإرجاعها بشكل موحد

#### 3. Business Services (`app/services/`)
- **المسؤولية:** Domain logic وقواعد العمل
- **مستقل تماماً عن:** HTTP, API, FastAPI
- **يمكن استخدامه من:** API, CLI, Background tasks, Tests

---

## 🔧 الاستخدام | Usage

### تشغيل مع Frontend (الافتراضي)

```python
# app/main.py
from app.core.config import get_settings
from app.kernel import RealityKernel

settings = get_settings()
kernel = RealityKernel(settings=settings)  # enable_static_files=True (default)
app = kernel.get_app()
```

**النتيجة:**
- ✅ API endpoints متاحة على `/api/*`
- ✅ Frontend متاح على `/`
- ✅ Static files (CSS, JS) متاحة

### تشغيل API-Only Mode

```python
# app/main.py
from app.core.config import get_settings
from app.kernel import RealityKernel

settings = get_settings()
kernel = RealityKernel(settings=settings, enable_static_files=False)
app = kernel.get_app()
```

**النتيجة:**
- ✅ API endpoints متاحة على `/api/*`
- ❌ لا frontend
- ❌ لا static files
- 🚀 أخف وأسرع

### Configuration

يمكنك التحكم في static files عبر environment variable:

```bash
# .env
ENABLE_STATIC_FILES=false  # للوضع API-only
```

```python
# app.core.config.py
class AppSettings(BaseSettings):
    ENABLE_STATIC_FILES: bool = True
```

---

## 📁 هيكل الملفات | File Structure

### API Core (إلزامي)
```
app/
├── api/                    # API Layer
│   ├── routers/            # Endpoints
│   │   ├── admin.py
│   │   ├── crud.py
│   │   ├── security.py
│   │   └── ...
│   └── schemas/            # Request/Response models
│
├── services/               # Business Logic
│   ├── boundaries/         # Facade services
│   │   ├── admin_chat_boundary_service.py
│   │   ├── auth_boundary_service.py
│   │   └── crud_boundary_service.py
│   ├── admin/
│   ├── chat/
│   └── ...
│
├── core/                   # Infrastructure
│   ├── database.py
│   ├── security.py
│   └── ...
│
├── kernel.py               # Application kernel (API-First)
└── main.py                 # Entry point
```

### Frontend (اختياري)
```
app/
├── static/                 # Frontend files (optional)
│   ├── index.html
│   ├── css/
│   └── js/
│
└── middleware/
    └── static_files_middleware.py  # Static serving (optional)
```

---

## ✅ قواعد الالتزام | Compliance Rules

### للـ API Routers

1. **لا business logic مطلقاً**
   ```python
   # ❌ خطأ
   @router.get("/users/{user_id}")
   async def get_user(user_id: int, db: Session = Depends(get_db)):
       user = db.query(User).filter(User.id == user_id).first()
       # معالجة معقدة...
       return user
   
   # ✅ صحيح
   @router.get("/users/{user_id}")
   async def get_user(
       user_id: int,
       service: UserBoundaryService = Depends(get_user_service)
   ):
       return await service.get_user(user_id)
   ```

2. **استخدام Pydantic schemas دائماً**
   ```python
   # ✅ Request validation
   @router.post("/users", response_model=UserResponse)
   async def create_user(
       data: UserCreateRequest,  # Pydantic model
       service: UserBoundaryService = Depends(get_user_service)
   ):
       return await service.create_user(data)
   ```

3. **Dependency injection للخدمات**
   ```python
   # ✅ صحيح
   def get_auth_service(db: AsyncSession = Depends(get_db)):
       return AuthBoundaryService(db)
   
   @router.post("/login")
   async def login(service: AuthBoundaryService = Depends(get_auth_service)):
       ...
   ```

### للـ Services

1. **مستقل عن HTTP/FastAPI**
   ```python
   # ✅ صحيح - لا imports من fastapi
   from sqlalchemy.ext.asyncio import AsyncSession
   
   class UserService:
       def __init__(self, db: AsyncSession):
           self.db = db
       
       async def create_user(self, email: str, name: str) -> User:
           # منطق العمل
           ...
   ```

2. **قابل للاستخدام من أي مكان**
   ```python
   # من API
   service = UserService(db)
   user = await service.create_user(email, name)
   
   # من CLI
   service = UserService(db)
   user = await service.create_user(email, name)
   
   # من Tests
   service = UserService(mock_db)
   user = await service.create_user(email, name)
   ```

---

## 🧪 الاختبار | Testing

### اختبار API Endpoints

```python
# tests/api/test_admin.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_admin_chat(client: AsyncClient):
    response = await client.post(
        "/admin/chat",
        json={"message": "Hello"}
    )
    assert response.status_code == 200
```

### اختبار Services (بدون API)

```python
# tests/services/test_user_service.py
import pytest
from app.services.users.service import UserService

@pytest.mark.asyncio
async def test_create_user(mock_db):
    service = UserService(mock_db)
    user = await service.create_user(
        email="test@example.com",
        name="Test User"
    )
    assert user.email == "test@example.com"
```

---

## 📊 المقاييس | Metrics

### قبل التحسين
- ❌ Static file serving في kernel.py
- ❌ لا يمكن تشغيل API بدون frontend
- ❌ Tight coupling بين API و UI

### بعد التحسين
- ✅ Static files منفصل في middleware
- ✅ يمكن تشغيل API-only mode
- ✅ Zero coupling بين API و UI
- ✅ 100% API-First Architecture

---

## 🔄 Migration Guide

### للمطورين الحاليين

إذا كان لديك كود يستخدم `setup_static_files` القديم:

```python
# القديم (Deprecated)
from app.core.static_handler import setup_static_files
setup_static_files(app)

# الجديد
from app.middleware.static_files_middleware import (
    StaticFilesConfig,
    setup_static_files_middleware
)

config = StaticFilesConfig(
    enabled=True,
    serve_spa=True,
)
setup_static_files_middleware(app, config)
```

### للأنظمة الخارجية

إذا كنت تستخدم CogniForge API:

1. **لا تغيير مطلوب** - جميع API endpoints لا تزال تعمل
2. **توصية:** استخدم `/api/*` endpoints بدلاً من الاعتماد على frontend
3. **فائدة:** يمكنك الآن استخدام API بدون تحميل frontend

---

## 📚 المراجع | References

- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [API-First Design](https://swagger.io/resources/articles/adopting-an-api-first-approach/)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)

---

**Built with ❤️ following API-First principles**
