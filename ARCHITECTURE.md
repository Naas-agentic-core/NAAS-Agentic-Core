# Architecture: Single Control Plane (Orchestrator Service)

## Core Principle
نقطة التحكم الواحدة للتشغيل (Control Plane) هي خدمة **`microservices/orchestrator_service`** عبر بوابة API Gateway فقط.

- Gateway (`microservices/api_gateway`) هو نقطة الدخول العامة الوحيدة.
- `orchestrator-service` هو المالك القانوني لتدفقات chat/missions.
- مسارات المونوليث في `app/api/routers/customer_chat.py` و`app/api/routers/admin.py` تعمل كـ **Compatibility Facades** فقط.

## Operational Rules
1. يمنع تنفيذ منطق الدردشة أو المهام محلياً داخل المونوليث.
2. أي تكامل بين الخدمات يتم عبر HTTP/WebSocket/Event Bus فقط.
3. `X-Correlation-ID` يجب أن ينتقل من Gateway إلى orchestrator-service عبر كل الطلبات.

## Rollback Strategy
- الإرجاع السريع يتم عبر revert commit الخاص بالقطع أو عبر feature flags للـ rollout.
- واجهات التوافق تبقى مفعلة حتى اكتمال parity وtelemetry.
