# 🧬 E-TAALEEM — GOD-TIER MICROSCOPIC AUTOPSY
## Incident ID: `REF-PROD-CATASTROPHE-099`

> **Mode:** Read-Only Forensic Reconstruction (No Fixes Applied)  
> **Role:** Supreme SRE-X & Principal Architect  
> **Date:** 2026-03-31

---

## 🎯 Executive Verdict

النظام لا يعاني من خللٍ واحد، بل من **ثلاثة مسارات انهيار متراكبة** تصنع ما وصفته بـ **Architectural Deception**:

1. **واجهة العرض (Frontend) لا تنزف JSON من WebSocket parser نفسه**، بل من تمرير محتوى `assistant_error.payload.content` كما هو إلى الرسائل بدون تعقيم إذا كان المحتوى نفسه نص JSON.
2. **طبقة الاسترجاع (RAG) منحازة بقيم افتراضية صلبة** (`2024` + `exercise_num=1`) عند أي فشل Parsing، فتُسحب النتائج نحو نفس عينة الامتحان مرارًا.
3. **مسار الأدوات الخارجية (Deep Research/Tavily/Admin)** يعتمد سياسة **Fail-Fast escalation**؛ أي خطأ في أداة البحث يصعد بسرعة إلى `assistant_error` event. هذا يعطي إحساس “instant crash” حتى مع وجود Fallbacks جزئية.

---

## 🔥 FRONT 1 — Frontend Blindness (Protocol Rendering Autopsy)

### Root Cause
الـ WebSocket handler يقوم بعمل `JSON.parse` بشكل صحيح، لكن rendering layer في hook الدردشة يعرض `payload.content` مباشرة عند `assistant_error`.

إذا كانت `content` نفسها عبارة عن JSON string (مثلاً `{"type":"assistant_error",...}`)، يتم عرضها كنص خام داخل الشات.

### Forensic Evidence
- `useRealtimeConnection.js` يفسر الإطار كـ JSON قبل البث الداخلي.
- `useAgentSocket.js` يضيف رسالة `Error: ${content}` دون أي تنقية/تحقق إضافي من كون content إطارًا متداخلًا.

### Impact
- المستخدم يرى “JSON bleeding” بدل رسالة بشرية.
- يختلط Data Plane (Protocol Frames) مع UX Plane (Renderable Text).

---

## 🧠 FRONT 2 — Cached Hallucination (Retriever/RAG Autopsy)

### Root Cause
لم يتم العثور على Mock ثابت لعبارة “2024 Baccalaureate” حرفيًا، ولم يتم العثور على `similarity_threshold = 0`.

**لكن تم إثبات السبب الأقوى:**
- عند فشل/نقص تحليل الاستعلام، النظام يحقن قيمًا افتراضية:
  - `year = 2024`
  - `exercise_num = 1`
  - أحيانًا subject heuristic (`احتمالات`) في fallback
- ثم يمرر هذه القيم إلى البحث الدلالي مع فلاتر exact، ما يؤدي لانحياز دائم لنفس الوثائق/التمرين.

### Forensic Evidence
- QueryAnalyzer defaults hardcoded داخل `search.py`.
- InternalRetrieverNode يستخدم `filters` المتولدة مباشرة في `semantic_search(...)`.

### Impact
- أي طلب تمرين غير واضح/مركب قد ينتهي لنفس نتيجة BAC 2024 بشكل متكرر.
- يظهر للمستخدم كـ “hallucination loop” بينما هو في الأصل “filter bias loop”.

---

## ⚡ FRONT 3 — External Tool Collapse (Tavily/Deep Research Autopsy)

### Root Cause (Composite)
1. **Tavily key path:** إذا لم يوجد `TAVILY_API_KEY`، النظام في بعض المسارات ينتقل لـ DuckDuckGo fallback (Degraded mode) وليس crash مباشر.
2. **لكن المسار التشغيلي الفعلي للأدوات يعتمد Fail-Fast escalation:**
   - `deep_research(...)` إذا أعاد خطأ/هيكل خطأ → يتم رفع استثناء.
   - الاستثناءات تُصعّد إلى طبقة المهمة، وتتحول إلى `assistant_error` event بسرعة.
3. هذا السلوك يخلق perception بأن “circuit breaker bypassed” لأن fallback ليس احتوائيًا على مستوى UX stream.

### Forensic Evidence
- `super_search.py` يقرأ `TAVILY_API_KEY` ويحوّل لبديل عند الغياب.
- `content.py` يطبق سياسة صريحة: propagate exceptions (Fail-Fast).
- `mission_complex.py` في `except` يولّد event من نوع `assistant_error`.

### Impact
- الاستعلامات الإدارية/البحث العميق تبدو وكأنها تنهار فورًا.
- واجهة المستخدم تستقبل error envelope بدل degradation narrative متدرّج.

---

## 🧾 X-RAY EVIDENCE TABLE (Canonical)

| Front | Forensic Finding & Root Cause | File:Line | Hard Evidence |
|-------|-------------------------------|-----------|---------------|
| 1. FRONTEND | Rendering blind spot: `assistant_error.payload.content` يُعرض مباشرة كنص | `frontend/app/hooks/useRealtimeConnection.js:49-53`, `frontend/app/hooks/useAgentSocket.js:149-150` | `JSON.parse(event.data)` ثم `content: \`Error: ${content}\`` بلا sanitization إضافي. |
| 2. RAG | Default-filter bias: fallback يثبت `year=2024` و`exercise_num=1` | `microservices/orchestrator_service/src/services/overmind/graph/search.py:62-67`, `:75-79`, `:104`, `:128` | `... else 2024`, `... else 1` ثم تمريرها إلى `semantic_search(... filters=exact_filters)`. |
| 3. TOOLS | Fail-fast escalation يحوّل أعطال البحث إلى `assistant_error` بسرعة | `microservices/research_agent/src/search_engine/super_search.py:121-141`, `app/services/chat/tools/content.py:184`, `:189-190`, `:153-155`, `microservices/orchestrator_service/src/services/overmind/utils/mission_complex.py:278-283` | Missing Tavily => fallback exists، لكن deep_research error => `raise` => `assistant_error` event في طبقة mission stream. |

---

## ✅ Negative Findings (Important)

- لم يتم العثور على نص mock ثابت لعبارة `2024 Baccalaureate` داخل الأكواد المفحوصة.
- لم يتم العثور على ضبط صريح `similarity_threshold = 0` في ملفات الاسترجاع/البحث التي تم تتبعها.
- مسارات الاستدعاء المتزامن الحساسة تم رصد تشغيلها غالبًا عبر `to_thread`/`run_in_executor`، لذا starvation ليس التفسير الأقوى هنا.

---

## 🧠 Final Architectural Diagnosis

**الحادثة ناتجة عن “مزيج سمّي” من: Protocol/Text boundary leakage + hardcoded retrieval defaults + aggressive fail-fast surfacing.**

هذا يفسر الأعراض الثلاثة معًا بدون افتراضات خارجية:
- JSON يظهر في الشات.
- نفس تمرين 2024 يتكرر.
- أدوات البحث تبدو وكأنها تنهار فورًا.

> **No fix included by design. This document is forensic-only.**
