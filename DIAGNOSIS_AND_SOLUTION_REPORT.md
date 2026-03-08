# تشخيص وحل مشكلة الإجابات العامة في دردشة الأدمن (100% Microservices StateGraph)

## 1. التشخيص الدقيق لجذر المشكلة (Root Cause Analysis)

### 1.1. ضعف التوجيه في `SupervisorNode` (عنق الزجاجة الأول)
في مسار الـ 100% Microservices StateGraph، تمر جميع الرسائل عبر `SupervisorNode` الموجود في `microservices/orchestrator_service/src/services/overmind/graph/main.py`.
المشكلة تكمن في أن هذا الموجه يعتمد على كلمات مفتاحية بسيطة جداً وغير كافية:
```python
query = state.get("query", "").lower()
if any(w in query for w in ["كم", "إحصائيات", "ملف", "ملفات"]):
    intent = "admin"
else:
    intent = "search"
```
هذا الشرط الهش يتجاهل الكثير من صيغ الأسئلة الإدارية (مثل "حساب عدد المستخدمين"، أو "كم عدد الجداول")، مما يؤدي إلى توجيهها بالخطأ إلى مسار البحث `search` بدلاً من مسار الإدارة `admin`.

### 1.2. قصور في `IntentDetector` وعدم ارتباطه بالـ Graph
حتى لو افترضنا أن نية المستخدم كانت موجهة عبر `IntentDetector`، نجد أن:
- التعبير النمطي (Regex) في `microservices/orchestrator_service/src/services/overmind/utils/intent_detector.py` ضمن `admin_queries` لا يحتوي على الأنماط الخاصة بحساب الملفات (مثل `count files` أو `حساب الملفات`).
- الأهم من ذلك، الـ StateGraph الجديد الموحد (`create_unified_graph`) **لا يستخدم `IntentDetector` أساساً** في `SupervisorNode` بل يكتفي بالشرط اليدوي المذكور أعلاه.

### 1.3. نقص وعي وكيل الإدارة `AdminAgentNode` (الـ Tools)
عندما ينجح التوجيه وتصل الرسالة إلى `AdminAgentNode` في `microservices/orchestrator_service/src/services/overmind/graph/admin.py`:
- **غياب أداة المستخدمين:** لا توجد أداة تُدعى `get_user_count` ضمن قائمة `ADMIN_TOOLS`. الوكيل الذكي (LLM) لا يملك طريقة لمعرفة عدد المستخدمين ويُجبر على إعطاء إجابة عامة بأنه لا يستطيع.
- **تنسيق المخرجات (JSON Stringification):** الأدوات الموجودة (مثل `count_python_files`, `count_db_tables`) تُرجع قواميس (Dictionaries).
في `ToolExecutorNode` يتم تحويلها إلى نصوص بشكل مباشر `str(res)`. هذا يؤدي لظهور مخرجات قبيحة بصيغة القاموس للمستخدم النهائي، مما يكسر تجربة المحادثة ويؤدي لإجابات غير متسقة من الوكيل.

---

## 2. الحل الشامل الكامل (Comprehensive Solution)

لحل هذه "الكارثة" بشكل كامل ضمن معمارية 100% Microservices و StateGraph، يجب إجراء التعديلات التالية:

### الخطوة الأولى: دمج `IntentDetector` في الـ StateGraph
يجب ترقية `SupervisorNode` ليكون غير متزامن `async` ويستعين بخدمة `IntentDetector` المتقدمة بدلاً من الشرط اليدوي الضعيف.

**التعديل في `microservices/orchestrator_service/src/services/overmind/graph/main.py`:**
```python
class SupervisorNode:
    async def __call__(self, state: AgentState) -> dict:
        import time
        from .telemetry import emit_telemetry
        from microservices.orchestrator_service.src.services.overmind.utils.intent_detector import IntentDetector, ChatIntent

        start_time = time.time()
        query = state.get("query", "")

        detector = IntentDetector()
        intent_result = await detector.detect(query)

        # الاعتماد على المكتشف الذكي
        if intent_result.intent == ChatIntent.ADMIN_QUERY:
            intent = "admin"
        else:
            intent = "search"

        emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
        return {"intent": intent}
```

### الخطوة الثانية: توسيع الأنماط في `IntentDetector`
يجب إضافة الكلمات المفتاحية الخاصة بالملفات والعد إلى التعبيرات النمطية.

**التعديل في `microservices/orchestrator_service/src/services/overmind/utils/intent_detector.py`:**
```python
        admin_queries = [
            r"(user|users|مستخدم|مستخدمين|count users|list users|profile|stats|أعضاء)",
            r"(database|schema|tables|db map|database map|قاعدة بيانات|قاعدة البيانات|جداول|مخطط|بنية البيانات|خريطة قاعدة البيانات|العلاقات)",
            r"(route|endpoint|api path|مسار api|نقطة نهاية|services|microservices|خدمات|مصغرة)",
            r"(structure|project info|هيكل المشروع|معلومات المشروع|بنية النظام)",
            r"(count files|حساب الملفات|ملفات|ملف|ملفات بايثون|python files|ملف بايثون|count python files|كم عدد)", # تمت الإضافة هنا
        ]
```

### الخطوة الثالثة: تزويد `AdminAgentNode` بالأدوات الناقصة وتصحيح المخرجات
يجب إضافة أداة `get_user_count` وجعل جميع الأدوات تُرجع نصوصاً (Strings) طبيعية باللغة العربية.

**التعديل في `microservices/orchestrator_service/src/services/overmind/graph/admin.py`:**
1. استيراد عميل المستخدمين:
```python
from microservices.orchestrator_service.src.infrastructure.clients.user_client import user_client
```

2. إضافة أداة المستخدمين:
```python
@kagent_tool(name="get_user_count", mcp_server="naas.tools.users")
async def get_user_count() -> str:
    """Get the exact count of total registered users."""
    try:
        count = await user_client.get_user_count()
        return f"عدد المستخدمين المسجلين في النظام هو: {count} مستخدم."
    except Exception as e:
        return f"تعذر الحصول على عدد المستخدمين: {e}"
```

3. تعديل الأدوات الحالية لتُرجع نصوصاً:
```python
@kagent_tool(name="count_python_files", mcp_server="naas.tools.filesystem")
def count_python_files() -> str:
    """Get the exact count of python files in the project."""
    result = subprocess.run(
        ["find", ".", "-type", "f", "-name", "*.py"], capture_output=True, text=True, check=False
    )
    count = len(result.stdout.strip().split("\n"))
    return f"عدد ملفات بايثون في المشروع هو: {count} ملف."

@kagent_tool(name="count_db_tables", mcp_server="naas.tools.database")
async def count_db_tables() -> str:
    """Get the exact count of database tables."""
    async with async_session_factory() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM information_schema.tables"))
        count = result.scalar() or 0
    return f"يوجد {count} جدول في قاعدة البيانات."
```

4. إضافة الأداة الجديدة لقائمة `ADMIN_TOOLS`:
```python
ADMIN_TOOLS = [count_python_files, count_db_tables, list_microservices, calculate_stats, get_user_count]
```

---

بتطبيق هذه التغييرات، ستصبح المنظومة قادرة على:
1. فهم نوايا المستخدم بدقة عالية بغض النظر عن طريقة الصياغة (حساب عدد، كم عدد، الخ) عبر الـ `IntentDetector`.
2. توجيه الطلب بذكاء إلى `AdminAgentNode` عبر الـ `SupervisorNode`.
3. تزويد الـ LLM بالأدوات الصحيحة (بما في ذلك المستخدمين).
4. عرض النتيجة النهائية للمستخدم بنص عربي سليم ومباشر بدلاً من قواميس JSON مشوهة.
