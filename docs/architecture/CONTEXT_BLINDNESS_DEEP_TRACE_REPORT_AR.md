# تقرير التتبع الجنائي العميق لعمى السياق (Generated)

## 1) النتيجة الكلية

تم العثور على **12 دليلًا صريحًا** موزعة على 6 مجموعات مخاطر تشغيلية.

## 2) توزيع المخاطر

| مجموعة المخاطر | عدد الأدلة |
|---|---:|
| anchor | 2 |
| drift | 1 |
| fallback | 1 |
| identity | 1 |
| transport | 4 |
| truncation | 3 |

## 3) سجل الأدلة القابل للتتبع

| الكود | الملف | السطر | الدلالة |
|---|---|---:|---|
| CB-CLI-01 | `frontend/app/hooks/useAgentSocket.js` | 146 | قص سياق العميل إلى آخر 30 رسالة. |
| CB-CLI-02 | `frontend/app/hooks/useAgentSocket.js` | 328 | إرسال conversation_id مشروط بتوفر الحالة لحظة الإرسال. |
| CB-CLI-03 | `frontend/public/js/legacy-app.jsx` | 446 | المسار legacy يغلق socket قبل إنشاء قناة جديدة. |
| CB-CLI-03 | `frontend/public/js/legacy-app.jsx` | 560 | المسار legacy يغلق socket قبل إنشاء قناة جديدة. |
| CB-CLI-03 | `frontend/public/js/legacy-app.jsx` | 780 | المسار legacy يغلق socket قبل إنشاء قناة جديدة. |
| CB-CLI-03 | `frontend/public/js/legacy-app.jsx` | 903 | المسار legacy يغلق socket قبل إنشاء قناة جديدة. |
| CB-SRV-05 | `microservices/orchestrator_service/src/api/context_utils.py` | 4 | وجود تحذير صريح من خطر الانجراف بين المسارات. |
| CB-SRV-04 | `microservices/orchestrator_service/src/api/context_utils.py` | 47 | قص الدمج النهائي للتاريخ إلى 80 عنصرًا. |
| CB-SRV-01 | `microservices/orchestrator_service/src/api/routes.py` | 68 | نافذة تاريخ model input محدودة إلى 24 رسالة. |
| CB-SRV-02 | `microservices/orchestrator_service/src/api/routes.py` | 191 | fallback بارد صامت عند غياب السياق. |
| CB-SRV-03 | `microservices/orchestrator_service/src/api/routes.py` | 249 | الاعتماد على استخراج مرساة إحالية heuristic. |
| CB-SRV-03 | `microservices/orchestrator_service/src/api/routes.py` | 331 | الاعتماد على استخراج مرساة إحالية heuristic. |

## 4) سلسلة الانهيار السببية (Causal Chain)

1. **client truncation** يقلص التاريخ قبل النقل.
2. **identity conditionality** قد ترسل follow-up دون هوية ثابتة.
3. **transport instability** في legacy يرفع احتمالات انقطاع التسلسل.
4. **server truncation** يقلص التاريخ مرة أخرى قبل graph input.
5. **cold-start fallback** يحول فشل السياق إلى استمرار صامت.
6. **heuristic anchor extraction** لا يعوض دائمًا فقد المرساة.
7. **path drift risk** يهدد توحيد السلوك بين المسارات.

## 5) مقتطفات أدلة خام

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

## 6) تشخيص جذري نهائي

السبب الجذري الأعلى: غياب عقد استمرارية سياق قابل للتحقق end-to-end (Identity + Integrity + Anchor Presence + Explicit Failure Semantics).

## 7) إغلاق هندسي قابل للقياس

- فرض حقول استمرارية إلزامية في follow-up.
- رفض صريح للحالات الإحالية دون anchor.
- توحيد المسار وإيقاف legacy في الإنتاج.
- تفعيل مقاييس ContextContractViolation وColdStartOnFollowup.

