# تقرير التشريح الجنائي العميق لعمى السياق (Generated)

## 1) لوحة القيادة التنفيذية

- **إجمالي الأدلة:** 12
- **النقاط الخام:** 102
- **الدرجة الموزونة:** 85/100
- **تصنيف الشدة:** حرج جدًا

## 2) توزيع المخاطر حسب المجموعة

| المجموعة | عدد الأدلة |
|---|---:|
| anchor | 2 |
| drift | 1 |
| fallback | 1 |
| identity | 1 |
| transport | 4 |
| truncation | 3 |

## 3) توزيع المخاطر حسب الطبقة

| الطبقة | عدد الأدلة |
|---|---:|
| client | 2 |
| governance | 1 |
| semantic | 2 |
| server | 3 |
| transport | 4 |

## 4) أعلى الأدلة خطورة

| الكود | الوزن | الملف | السطر | الدلالة |
|---|---:|---|---:|---|
| CB-CLI-02 | 10 | `frontend/app/hooks/useAgentSocket.js` | 328 | إرسال conversation_id مشروط بتوفره في الحالة اللحظية. |
| CB-SRV-02 | 10 | `microservices/orchestrator_service/src/api/routes.py` | 191 | fallback بارد صامت عند فقد السياق. |
| CB-CLI-03 | 9 | `frontend/public/js/legacy-app.jsx` | 446 | المسار legacy يعيد تدوير socket لكل إرسال. |
| CB-CLI-03 | 9 | `frontend/public/js/legacy-app.jsx` | 560 | المسار legacy يعيد تدوير socket لكل إرسال. |
| CB-CLI-03 | 9 | `frontend/public/js/legacy-app.jsx` | 780 | المسار legacy يعيد تدوير socket لكل إرسال. |
| CB-CLI-03 | 9 | `frontend/public/js/legacy-app.jsx` | 903 | المسار legacy يعيد تدوير socket لكل إرسال. |

## 5) سجل الأدلة الكامل

| الكود | الطبقة | المجموعة | الوزن | الملف | السطر |
|---|---|---|---:|---|---:|
| CB-CLI-01 | client | truncation | 8 | `frontend/app/hooks/useAgentSocket.js` | 146 |
| CB-CLI-02 | client | identity | 10 | `frontend/app/hooks/useAgentSocket.js` | 328 |
| CB-CLI-03 | transport | transport | 9 | `frontend/public/js/legacy-app.jsx` | 446 |
| CB-CLI-03 | transport | transport | 9 | `frontend/public/js/legacy-app.jsx` | 560 |
| CB-CLI-03 | transport | transport | 9 | `frontend/public/js/legacy-app.jsx` | 780 |
| CB-CLI-03 | transport | transport | 9 | `frontend/public/js/legacy-app.jsx` | 903 |
| CB-SRV-05 | governance | drift | 9 | `microservices/orchestrator_service/src/api/context_utils.py` | 4 |
| CB-SRV-04 | server | truncation | 7 | `microservices/orchestrator_service/src/api/context_utils.py` | 47 |
| CB-SRV-01 | server | truncation | 8 | `microservices/orchestrator_service/src/api/routes.py` | 68 |
| CB-SRV-02 | server | fallback | 10 | `microservices/orchestrator_service/src/api/routes.py` | 191 |
| CB-SRV-03 | semantic | anchor | 7 | `microservices/orchestrator_service/src/api/routes.py` | 249 |
| CB-SRV-03 | semantic | anchor | 7 | `microservices/orchestrator_service/src/api/routes.py` | 331 |

## 6) سلسلة الانهيار السببية

1. قص مبكر للسياق في العميل.
2. احتمال إرسال follow-up بلا هوية ثابتة.
3. لااستقرار نقلي في مسار legacy.
4. قص إضافي للسياق في الخادم.
5. fallback بارد صامت.
6. اعتماد recovery heuristic.
7. خطر drift بين المسارات.

## 7) مقتطفات دليل خام

- `CB-CLI-01` @ `frontend/app/hooks/useAgentSocket.js:146` → `return normalized.slice(-30);`
- `CB-CLI-02` @ `frontend/app/hooks/useAgentSocket.js:328` → `if (conversationId !== null && conversationId !== undefined) {`
- `CB-CLI-03` @ `frontend/public/js/legacy-app.jsx:446` → `socketRef.current.close();`
- `CB-CLI-03` @ `frontend/public/js/legacy-app.jsx:560` → `socketRef.current.close();`
- `CB-CLI-03` @ `frontend/public/js/legacy-app.jsx:780` → `socketRef.current.close();`
- `CB-CLI-03` @ `frontend/public/js/legacy-app.jsx:903` → `socketRef.current.close();`
- `CB-SRV-05` @ `microservices/orchestrator_service/src/api/context_utils.py:4` → `DO NOT modify without updating the monolith counterpart.`
- `CB-SRV-04` @ `microservices/orchestrator_service/src/api/context_utils.py:47` → `return merged_history[-80:]`
- `CB-SRV-01` @ `microservices/orchestrator_service/src/api/routes.py:68` → `MAX_HISTORY_MESSAGES = 24`
- `CB-SRV-02` @ `microservices/orchestrator_service/src/api/routes.py:191` → `logger.warning("No context available - cold start")`
- `CB-SRV-03` @ `microservices/orchestrator_service/src/api/routes.py:249` → `def _extract_recent_entity_anchor(history_messages: list[dict[str, str]] | None) -> str | None:`
- `CB-SRV-03` @ `microservices/orchestrator_service/src/api/routes.py:331` → `anchor = _extract_recent_entity_anchor(history_messages)`

## 8) تشخيص جذري نهائي

السبب الجذري الأعلى: غياب عقد استمرارية سياق قابل للتحقق (Identity + Integrity + Anchor + Explicit Failure).

## 9) إجراءات إغلاق فورية

- فرض Context Continuity Contract على follow-up.
- رفض صريح لأي follow-up إحالي دون anchor.
- إيقاف legacy path في الإنتاج الحرج.
- تفعيل مقاييس violations والانحراف البارد.

