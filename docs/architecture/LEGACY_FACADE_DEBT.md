# Legacy Facade Debt Register (Controlled, Temporary)

هذا المستند يسجل الديون المعمارية المتبقية بعد احتواء مخاطر split-brain.

## Active Compatibility Facades

1. `app/api/routers/admin.py`
   - الحالة: Compatibility façade.
   - السلطة التنفيذية القانونية: `app.services.chat.orchestrator.ChatOrchestrator`.
   - ملاحظة: يبقى ingress نشطًا للتوافق مع الواجهات الحالية.

2. `app/api/routers/customer_chat.py`
   - الحالة: Compatibility façade.
   - السلطة التنفيذية القانونية: `app.services.chat.orchestrator.ChatOrchestrator`.
   - ملاحظة: يحافظ على عقود WS/HTTP الحالية مع التفويض.

3. `app/api/routers/content.py`
   - الحالة: Compatibility façade (content domain bridge).
   - السلطة التنفيذية القانونية: `research-agent` عبر ownership registry.

## Guards Enforced

- وسم صريح `COMPATIBILITY_FACADE_MODE=True` في المسارات المتبقية.
- اختبار معماري يفشل CI عند غياب الوسم أو تضارب authority.
- سجل ملكية route ownership يمنع legacy target افتراضيًا للمسارات الحرجة.

## Exit Criteria

لا يتم حذف واجهات التوافق إلا بعد:
1. إثبات parity بعقود واختبارات.
2. صفر استخدام فعلي في telemetry.
3. خطة rollback موثقة.


## Conversation-Service Promotion Criteria

لا تتم ترقية Conversation Service إلى هدف إنتاجي critical إلا إذا تحقق:
1. `CONVERSATION_PARITY_VERIFIED=true`.
2. `CONVERSATION_CAPABILITY_LEVEL` ضمن {`parity_ready`, `production_eligible`}.
3. نجاح اختبارات contract/parity الخاصة بـ HTTP وWS.
4. وجود خطة rollback تؤدي فورًا للرجوع إلى orchestrator كهدف قانوني.
