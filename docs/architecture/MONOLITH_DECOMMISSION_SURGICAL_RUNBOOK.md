[ASSUMPTION: لا توجد حالياً قياسات إنتاجية رقمية فعلية داخل المستودع لعدد اتصالات WS/الساعة أو أحجام الرسائل؛ لذلك كل رقم Rollout أدناه مرتبط مباشرة بصيغ قياس من Prometheus يجب تعبئتها بقيم آخر 7 أيام قبل التنفيذ.] 
[ASSUMPTION: ملف `microservices/orchestrator_service/api/routers/chat.py` المذكور في المتطلبات غير موجود في الشجرة الحالية، والملف الفعلي هو `microservices/orchestrator_service/src/api/routes.py`.] 

[FILE: microservices/api_gateway/main.py] [FUNCTION: chat_ws_proxy] [ACTION: تثبيت البوابة كنقطة دخول وحيدة لـ `/api/chat/ws` مع تمرير الاتصال إلى `_resolve_chat_ws_target` ثم `websocket_proxy`؛ منع أي اتصال مباشر من Next.js إلى `app/api/routers/customer_chat.py`.] [REASON: الدالة الحالية تسجل route_id وتطبق قرار توجيه مركزي، وأي bypass يلغي rollback الفوري على مستوى متغيرات البيئة.] 
[FILE: microservices/api_gateway/main.py] [FUNCTION: admin_chat_ws_proxy] [ACTION: تطبيق نفس قاعدة بوابة الدخول الوحيدة لمسار الأدمن `/admin/api/chat/ws` وربط sticky decision بنفس منطق `_resolve_chat_ws_target`.] [REASON: ضمان تماثل سلوك customer/admin أثناء التحويل؛ اختلاف المسارين الآن فقط في route_id.] 
[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_ws_target] [ACTION: اعتماد identity = `f"{route_id}:{upstream_path}"` كخوارزمية sticky الحالية، ثم توثيقها كـ Contract Routing Key غير قابل للتغيير خلال rollout.] [REASON: أي تعديل لصيغة identity يغيّر توزيع buckets ويكسر ثبات session placement.] 
[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_target_base] [ACTION: إبقاء شرط `CONVERSATION_PARITY_VERIFIED && CONVERSATION_CAPABILITY_LEVEL in {parity_ready, production_eligible}` قبل تفعيل التوجيه إلى conversation-service.] [REASON: الدالة تسقط تلقائياً إلى orchestrator-service عند غياب parity؛ هذا هو Safety Interlock الرسمي.] 
[FILE: microservices/api_gateway/config.py] [FUNCTION: Settings.validate_security_and_discovery] [ACTION: منع إعداد `ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT > 0` في production إلا إذا كانت parity مثبتة وقدرة الخدمة production_eligible.] [REASON: validation هنا تمنع split-brain الناتج عن رفع النسبة بالخطأ مع خدمة conversation غير جاهزة.] 
[FILE: app/api/routers/customer_chat.py] [FUNCTION: chat_stream_ws] [ACTION: وسم المسار كـ Compatibility Facade فقط وإضافة عدّاد `compatibility_facade_ws_sessions_total{scope="customer"}` قبل الحلقة `while True`.] [REASON: الدالة ما زالت قابلة لاستقبال اتصال مباشر إذا مرّ خارج البوابة؛ يلزم قياس واضح قبل purge.] 
[FILE: app/api/routers/admin.py] [FUNCTION: chat_stream_ws] [ACTION: إضافة نفس العدّاد للمسار الإداري وربطه بـ `scope="admin"`.] [REASON: purge آمن يتطلب إثبات أن volume المباشر = 0 على customer وadmin لمدة نافذة زمنية موحدة.] 
[FILE: app/services/chat/event_protocol.py] [FUNCTION: normalize_streaming_event] [ACTION: اعتماد هذه الدالة كمحوّل عقد وحيد قبل Next.js وتعطيل أي serialization بديل في facades.] [REASON: وجود راية `CHAT_USE_UNIFIED_EVENT_ENVELOPE` يعني أن العقد قد يتغير ثنائياً؛ يلزم نقطة تحويل واحدة قابلة للاختبار.] 
[FILE: microservices/orchestrator_service/src/api/routes.py] [FUNCTION: chat_ws_stategraph] [ACTION: تثبيت رسالة `conversation_init` كأول event بعد التوثيق وقبل streaming.] [REASON: هذه الرسالة هي المفتاح الوحيد المتاح حالياً لإسناد conversation_id واستمرار الجلسات الهجينة.] 
[FILE: microservices/orchestrator_service/src/api/routes.py] [FUNCTION: admin_chat_ws_stategraph] [ACTION: تطبيق نفس القاعدة مع التحقق الإداري `_is_admin_payload` قبل accept.] [REASON: منع تسريب جلسة non-admin إلى قناة admin أثناء التحويل.] 
[FILE: microservices/conversation_service/main.py] [FUNCTION: _chat_ws_loop] [ACTION: استبدال envelope الحالي `{status,response,route_id}` بعقد موحّد مطابق لـ `normalize_streaming_event` قبل أي rollout > 0.] [REASON: envelope الحالي لا يحتوي `type/payload` ويؤدي إلى silent break في واجهة Next.js عند التحويل.] 
[FILE: microservices/api_gateway/legacy_acl/adapter.py] [FUNCTION: websocket_target] [ACTION: الإبقاء على هذا المسار كمنفذ legacy وحيد أثناء فترة rollback فقط، ثم حذفه في purge النهائي.] [REASON: `CORE_KERNEL_URL` مقصور هنا تشغيلياً؛ هذا يسهّل إيقاف monolith بإزالة وحدة واحدة.] 
[FILE: config/routes_registry.json] [FUNCTION: N/A] [ACTION: تحديث owner لمساري `/api/chat/ws` و`/admin/api/chat/ws` إلى `conversation-service` فقط بعد إتمام 100% rollout + 7 أيام استقرار.] [REASON: registry يستخدم كمرجع حوكمة؛ التحديث المبكر يخلق drift بين الواقع والحوكمة.] 

[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_ws_target] [ACTION: رسم الاعتماديات التنفيذية الدقيقة:] [REASON: تثبيت مسار الاستدعاء الحالي قبل أي قطع.] 

```
Next.js client
  -> WS /api/chat/ws (or /admin/api/chat/ws)
     -> microservices/api_gateway/main.py:chat_ws_proxy|admin_chat_ws_proxy
        -> _record_ws_session_metric(route_id)
        -> _resolve_chat_ws_target(route_id, upstream_path)
           -> _resolve_chat_target_base(route_id, identity, ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT)
              -> _should_route_to_conversation(identity, rollout_percent)
                 -> _rollout_bucket(identity)
              -> settings.CONVERSATION_PARITY_VERIFIED
              -> settings.CONVERSATION_CAPABILITY_LEVEL
              -> settings.CONVERSATION_SERVICE_URL | settings.ORCHESTRATOR_SERVICE_URL
           -> _conversation_ws_base_url() | _to_ws_base_url(target_base)
        -> websocket_proxy(websocket, target_url)
           -> target: orchestrator_service/src/api/routes.py:chat_ws_stategraph|admin_chat_ws_stategraph
              -> _ensure_conversation(...)
              -> send_json({"type":"conversation_init", ...})
              -> _stream_chat_langgraph(...)

Legacy direct path (still present, must be drained):
Next.js or internal caller
  -> core kernel app/api/routers/customer_chat.py:chat_stream_ws
     -> orchestrator_client.chat_with_agent(...)
     -> normalize_streaming_event(event)
  -> core kernel app/api/routers/admin.py:chat_stream_ws
     -> orchestrator_client.chat_with_agent(...)
     -> normalize_streaming_event(event)

Legacy ACL path (rollback only):
api_gateway/legacy_acl/adapter.py:websocket_target
  -> settings.CORE_KERNEL_URL (ws)
```

[FILE: microservices/api_gateway/main.py] [FUNCTION: chat_ws_proxy] [ACTION: تعريف نقاط الفشل الأحادية الحالية (SPOF):] [REASON: ربط rollback trigger بمكوّن محدد.] 
[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_ws_target] [ACTION: SPOF-1 = فشل DNS/health لـ conversation-service أو orchestrator-service.] [REASON: كل WS يمر عبر gateway ثم target واحد؛ تعطل أي target يسبب انقطاع فتح جلسات جديدة.] 
[FILE: microservices/api_gateway/main.py] [FUNCTION: chat_ws_proxy] [ACTION: SPOF-2 = تعطل websocket_proxy أو استهلاك event-loop في gateway.] [REASON: حتى مع targets سليمة، فشل proxy layer يمنع relay للرسائل ثنائياً.] 
[FILE: app/services/chat/event_protocol.py] [FUNCTION: normalize_streaming_event] [ACTION: SPOF-3 = drift في schema عند تبديل `CHAT_USE_UNIFIED_EVENT_ENVELOPE`.] [REASON: Next.js يعتمد shape محدد؛ drift صامت يظهر كرسائل لا تُعرض لا كأخطاء HTTP.] 
[FILE: microservices/orchestrator_service/src/api/routes.py] [FUNCTION: _ensure_conversation] [ACTION: SPOF-4 = فشل إنشاء/ربط conversation_id.] [REASON: الدالة تُستدعى قبل البث؛ الفشل يمنع session continuity.] 

[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_ws_target] [ACTION: تحليل Session State أثناء التحويل:] [REASON: تحديد ما يحدث للجلسة النشطة بدقة.] 
[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_ws_target] [ACTION: القرار يُتخذ عند handshake فقط؛ الجلسة المفتوحة تبقى على target الأصلي حتى الإغلاق.] [REASON: لا يوجد reconnect داخلي داخل proxy لنقل socket حي.] 
[FILE: frontend (consumer runtime)] [FUNCTION: WebSocket reconnect handler] [ACTION: الجلسة تنتقل إلى target جديد فقط عند reconnect؛ يجب تثبيت نفس `conversation_id` في payload التالي.] [REASON: النقل الحي intra-connection غير مدعوم بالبنية الحالية.] 

[FILE: microservices/orchestrator_service/src/api/routes.py] [FUNCTION: chat_ws_stategraph] [ACTION: بروتوكول ترحيل الجلسات postgres-core -> postgres-conv بدون قطع:] [REASON: الحفاظ على conversation continuity.] 
[FILE: microservices/orchestrator_service/src/api/routes.py] [FUNCTION: chat_ws_stategraph] [ACTION: Step-1 عند استقبال `conversation_id` من عميل بدأ على monolith، استدعِ `conversation_service` عبر API `POST /api/v1/conversations/import` (يُضاف) مع idempotency key = `{conversation_id}:{user_id}`.] [REASON: ضمان نقل lazy-on-access بدل batch ضخم يضغط DB.] 
[FILE: microservices/conversation_service/main.py] [FUNCTION: new endpoint import_conversation] [ACTION: Step-2 إنشاء endpoint استيراد idempotent ينسخ metadata + آخر N رسائل من postgres-core إلى postgres-conv داخل transaction واحدة.] [REASON: معالجة الجلسات الهجينة تتطلب نقطة استيراد ذرية.] 
[FILE: app/core/database + migration job] [FUNCTION: backfill_conversations_batch] [ACTION: Step-3 تشغيل backfill ليلي بحجم دفعة = `min(5000, floor(IOPS_free*0.4))` جلسة/دفعة.] [REASON: الرقم مشتق من سقف IOPS المتاح وليس قيمة عشوائية.] 
[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_ws_target] [ACTION: Step-4 sticky routing = hash(session_id) وليس hash(route_id:path) بإضافة header `X-Session-Id` من Next.js واستخدامه كـ identity.] [REASON: الـ identity الحالي لا يفرّق بين الجلسات المختلفة على نفس المسار.] 
[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_ws_target] [ACTION: البديل المرفوض: sticky على user_id فقط.] [REASON: user_id يدمج جلسات متعددة لنفس المستخدم ويمنع canary granular على مستوى session.] 

[FILE: app/services/chat/event_protocol.py] [FUNCTION: normalize_streaming_event] [ACTION: تعريف عقد JSON Schema الرسمي المتوافق مع Next.js:] [REASON: إزالة الغموض ومنع drift.] 

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://cogniforge.local/schemas/chat-event-envelope.schema.json",
  "type": "object",
  "required": ["type", "payload"],
  "properties": {
    "type": {
      "type": "string",
      "enum": [
        "assistant_delta",
        "assistant_final",
        "assistant_error",
        "status",
        "conversation_init",
        "complete"
      ]
    },
    "payload": {
      "type": "object",
      "properties": {
        "content": {"type": "string"},
        "details": {"type": "string"},
        "status_code": {"type": "integer"},
        "conversation_id": {"type": "integer"}
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": false
}
```

[FILE: tests/contracts/test_chat_event_contract.py] [FUNCTION: test_provider_events_match_schema] [ACTION: إنشاء اختبار Provider Contract يمرر عينات events من `normalize_streaming_event` ومن `chat_ws_stategraph` على schema أعلاه عبر `jsonschema.validate`.] [REASON: التحقق البرمجي قبل الدمج يمنع breaking changes غير مرئية.] 
[FILE: tests/contracts/pacts/nextjs-chat-consumer.json] [FUNCTION: generated by pact verifier] [ACTION: اعتماد Pact Consumer من Next.js يحدد أن `assistant_delta.payload.content` مطلوب عند type=assistant_delta.] [REASON: front-end هو مصدر الحقيقة لسلوك العرض.] 
[FILE: .github/workflows/ci.yml] [FUNCTION: job contract-drift] [ACTION: إضافة مرحلة تفشل إذا تغيّر hash لملف schema دون تحديث نسخة pact (`sha256(schema) == metadata.schema_hash`).] [REASON: كشف Silent Schema Drift تلقائياً.] 
[FILE: .github/workflows/ci.yml] [FUNCTION: job contract-drift] [ACTION: البديل المرفوض: الاكتفاء باختبارات وحدة normalize_streaming_event.] [REASON: unit tests لا تتحقق من عقد المستهلك Next.js ولا من events القادمة من orchestrator مباشرة.] 

[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_ws_target] [ACTION: خطة Rollout تدريجي محسوبة:] [REASON: كل قفزة مرتبطة بقياسات فعلية.] 
[FILE: Prometheus] [FUNCTION: query ws_conn_per_hour] [ACTION: احسب الأساس `C = avg_over_time(sum(rate(ws_handshake_total[5m]))[7d:1h]) * 3600`.] [REASON: عدد الاتصالات/ساعة من آخر 7 أيام.] 
[FILE: Prometheus] [FUNCTION: query ws_bytes_per_session] [ACTION: احسب `B = sum(rate(ws_bytes_total[5m])) / sum(rate(ws_sessions_total[5m]))`.] [REASON: متوسط البيانات/جلسة.] 
[FILE: Prometheus] [FUNCTION: query peak_hour] [ACTION: احسب `P95_peak = quantile_over_time(0.95, ws_conn_per_hour[7d])`.] [REASON: تحديد حمل الذروة الفعلي.] 
[FILE: rollout/runbook] [FUNCTION: phase_schedule] [ACTION: Phase-0 = 0% لمدة 24 ساعة baseline.] [REASON: جمع SLI baseline لنفس نافذة الأسبوع.] 
[FILE: rollout/runbook] [FUNCTION: phase_schedule] [ACTION: Phase-1 = `max(1, floor(200 / C * 100))%` لمدة 2 ساعة خارج الذروة.] [REASON: سقف 200 جلسة/ساعة canary كافٍ لاكتشاف أخطاء دون تعريض حجم كبير.] 
[FILE: rollout/runbook] [FUNCTION: phase_schedule] [ACTION: Phase-2 = `min(5, floor(1000 / C * 100))%` لمدة 6 ساعات.] [REASON: توسيع العينة إلى 1000 جلسة/ساعة كحد مراقب.] 
[FILE: rollout/runbook] [FUNCTION: phase_schedule] [ACTION: Phase-3 = 15% لمدة 24 ساعة تتضمن ساعة ذروة واحدة على الأقل.] [REASON: اختبار سلوك الذروة وليس فقط off-peak.] 
[FILE: rollout/runbook] [FUNCTION: phase_schedule] [ACTION: Phase-4 = 30% لمدة 24 ساعة.] [REASON: فحص استقرار نصف-حمولة.] 
[FILE: rollout/runbook] [FUNCTION: phase_schedule] [ACTION: Phase-5 = 50% لمدة 48 ساعة.] [REASON: إثبات تحمل فشل جزئي أثناء حمل كبير.] 
[FILE: rollout/runbook] [FUNCTION: phase_schedule] [ACTION: Phase-6 = 100% لمدة 7 أيام قبل purge.] [REASON: تغطية أنماط استخدام أسبوعية كاملة.] 

[FILE: rollout/gates] [FUNCTION: success_criteria] [ACTION: شرط الانتقال بين المراحل: `ws_open_success_rate >= 99.5%` لكل نافذة 30 دقيقة.] [REASON: أقل من ذلك يعني فشل handshake ملحوظ.] 
[FILE: rollout/gates] [FUNCTION: success_criteria] [ACTION: شرط الانتقال: `p95_end_to_end_latency_ms <= baseline_p95 * 1.15`.] [REASON: السماح بانحراف 15% كحد أعلى مقبول أثناء canary.] 
[FILE: rollout/gates] [FUNCTION: success_criteria] [ACTION: شرط الانتقال: `assistant_error_event_rate <= 0.5%` من إجمالي events.] [REASON: قياس صحة المحتوى وليس النقل فقط.] 
[FILE: rollout/gates] [FUNCTION: rollback_trigger] [ACTION: Rollback فوري إلى 0% إذا `ws_open_success_rate < 98.5%` خلال نافذتين متتاليتين (كل نافذة 5 دقائق).] [REASON: انخفاض >1.5 نقطة خلال 10 دقائق يمثل انقطاعاً واضحاً.] 
[FILE: rollout/gates] [FUNCTION: rollback_trigger] [ACTION: Rollback فوري إذا `p99_latency_ms > 2 * baseline_p99` لمدة 15 دقيقة.] [REASON: تضاعف p99 يعكس اختناق حاد.] 
[FILE: rollout/gates] [FUNCTION: rollback_trigger] [ACTION: Rollback فوري إذا `conversation_init_missing_rate > 0.1%`.] [REASON: غياب conversation_id يكسر استمرارية الجلسة الهجينة.] 
[FILE: rollout/gates] [FUNCTION: rollback_trigger] [ACTION: البديل المرفوض: rollback يدوي بناءً على ملاحظة logs فقط.] [REASON: الاستجابة اليدوية أبطأ من نافذة الضرر في WS الحي.] 

[FILE: purge/runbook] [FUNCTION: deletion_order] [ACTION: ترتيب الحذف 1: اضبط `ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT=100` و`ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT=100` في بيئة الإنتاج.] [REASON: تثبيت الوجهة الجديدة قبل إزالة المسارات القديمة.] 
[FILE: purge/runbook] [FUNCTION: deletion_order] [ACTION: ترتيب الحذف 2: حذف تعاريف compatibility WS من `app/api/routers/customer_chat.py:chat_stream_ws` و`app/api/routers/admin.py:chat_stream_ws` بعد إثبات direct traffic=0 لمدة 7 أيام.] [REASON: إزالة نقاط دخول monolith.] 
[FILE: purge/runbook] [FUNCTION: deletion_order] [ACTION: ترتيب الحذف 3: حذف `microservices/api_gateway/legacy_acl/adapter.py` وأي استدعاء له.] [REASON: إغلاق آخر منفذ `CORE_KERNEL_URL`.] 
[FILE: purge/runbook] [FUNCTION: deletion_order] [ACTION: ترتيب الحذف 4: إزالة `CORE_KERNEL_URL` من `microservices/api_gateway/config.py` والتحقق من مرور `scripts/fitness/check_core_kernel_acl.py`.] [REASON: منع regression يعيد ربط النواة القديمة.] 
[FILE: purge/runbook] [FUNCTION: deletion_order] [ACTION: ترتيب الحذف 5: حذف خدمة core-kernel من `docker-compose.yml` (غير موجودة حالياً في هذا المستودع، تحقق من compose الإنتاجي الفعلي قبل التنفيذ).] [REASON: إيقاف البنية نهائياً بعد قطع كل التبعيات.] 

[FILE: data-retention/policy] [FUNCTION: postgres_core_archive] [ACTION: الاحتفاظ بجداول `conversations`, `chat_messages`, `user_sessions`, `audit_logs` من postgres-core في مخزن أرشيف S3 Glacier عبر dump مشفر AES-256.] [REASON: تحقيق متطلبات traceability والتحقيقات.] 
[FILE: data-retention/policy] [FUNCTION: postgres_core_archive] [ACTION: مدة الاحتفاظ: 13 شهراً للـ chat business records و36 شهراً لـ audit_logs.] [REASON: 13 شهر يغطي مقارنة سنة-بسنة + شهر؛ 36 شهر للتدقيق الأمني طويل الأمد.] 
[FILE: data-retention/policy] [FUNCTION: postgres_core_archive] [ACTION: البديل المرفوض: حذف فوري كامل لـ postgres-core بعد cutover.] [REASON: يفقد القدرة على التحقيق في شكاوى متأخرة أو متطلبات قانونية.] 

[FILE: app/main.py] [FUNCTION: application bootstrap] [ACTION: checklist نظافة ما بعد الحذف:] [REASON: إثبات عدم وجود اعتماد متبقٍ على monolith.] 
[FILE: app/main.py] [FUNCTION: imports] [ACTION: `rg -n "customer_chat|admin\.chat_stream_ws|CORE_KERNEL_URL|legacy_acl" app/main.py app/ microservices/` يجب أن يعيد صفر نتائج تشغيلية.] [REASON: كشف أي مرجع متبقٍ.] 
[FILE: tests/governance/test_gateway_structure.py] [FUNCTION: test_only_legacy_acl_references_core_kernel_url] [ACTION: يجب أن يفشل الاختبار إذا عاد أي مرجع جديد لـ CORE_KERNEL_URL خارج ACL؛ بعد purge عدّل الاختبار ليتوقع صفر مراجع نهائياً.] [REASON: تحويل قيد الحوكمة من "محصور" إلى "ممنوع كلياً".] 
[FILE: CI] [FUNCTION: required_checks_before_shutdown] [ACTION: نجاح إلزامي لـ `pytest tests/contracts tests/governance` + `scripts/fitness/check_core_kernel_acl.py` + `scripts/fitness/check_core_kernel_env_profile.py`.] [REASON: هذه المجموعة تغطي العقد + الحوكمة + بيئة التشغيل.] 

[FILE: slo/spec] [FUNCTION: websocket_sla] [ACTION: تعريف SLO-1 = `WS handshake success >= 99.5%` على نافذة متحركة 30 دقيقة.] [REASON: يعكس توافر نقطة الدخول.] 
[FILE: slo/spec] [FUNCTION: websocket_sla] [ACTION: تعريف SLO-2 = `p95 message roundtrip <= 800ms` و`p99 <= 2000ms` على نافذة 15 دقيقة.] [REASON: يوازن بين تجربة المستخدم وتقلب الذروة.] 
[FILE: slo/spec] [FUNCTION: websocket_sla] [ACTION: تعريف SLO-3 = `assistant_error events <= 0.5%` على نافذة 30 دقيقة.] [REASON: يراقب جودة الاستجابة الدلالية.] 
[FILE: slo/spec] [FUNCTION: reconnect_policy] [ACTION: سياسة reconnect في Next.js = backoff 1s,2s,4s,8s, max 30s مع حد 8 محاولات ثم surfacing error UI.] [REASON: تقليل الضغط أثناء الأعطال مع سقف زمني واضح.] 
[FILE: Grafana dashboard ws-cutover] [FUNCTION: required_panels] [ACTION: لوحات إلزامية: `ws_handshake_total`, `ws_open_success_rate`, `ws_active_connections`, `ws_close_code_count{code}`, `chat_event_type_total{type}`, `conversation_init_missing_rate`, `schema_validation_fail_total`, `gateway_proxy_error_total`, `target_service_latency_ms{service}`.] [REASON: ربط النقل + العقد + الوجهة في لوحة واحدة.] 

[FILE: microservices/api_gateway/main.py] [FUNCTION: _resolve_chat_ws_target] [ACTION: قرار معماري رئيسي: تحويل مركزي في gateway مع rollout by env.] [REASON: rollback فوري بدون إعادة نشر Next.js.] [REJECTED-ALTERNATIVE: تحويل داخل Next.js حسب feature flag.] [REJECTION-REASON: يزيد surface area ويعقّد توحيد telemetry بين العملاء.] 
[FILE: app/services/chat/event_protocol.py] [FUNCTION: normalize_streaming_event] [ACTION: قرار معماري رئيسي: عقد events موحّد يمر عبر محوّل واحد.] [REASON: منع تباين provider payloads.] [REJECTED-ALTERNATIVE: قبول صيغ متعددة في Next.js parser.] [REJECTION-REASON: ينقل التعقيد للواجهة ويصعّب اكتشاف drift.] 
[FILE: microservices/orchestrator_service/src/api/routes.py] [FUNCTION: chat_ws_stategraph] [ACTION: قرار معماري رئيسي: lazy migration on first access للجلسات.] [REASON: تجنّب downtime المرتبط بعملية bulk migration قبل cutover.] [REJECTED-ALTERNATIVE: batch migration كاملة قبل rollout.] [REJECTION-REASON: مخاطرة زمنية عالية واحتمال قفل جداول الإنتاج.] 

[FILE: APPENDIX] [FUNCTION: code excerpts for surgical prompt grounding] [ACTION: إلحاق المقاطع الفعلية المطلوبة `chat_ws_proxy`, `_resolve_chat_ws_target`, `normalize_streaming_event`.] [REASON: تحويل الخطة من معمارية عامة إلى runbook قائم على الكود الفعلي.] 

```python
# microservices/api_gateway/main.py

def _resolve_chat_ws_target(route_id: str, upstream_path: str) -> str:
    """يحدد هدف WS الحديث باستخدام نفس محرك القرار الخاص بمسار HTTP."""
    identity = f"{route_id}:{upstream_path}"
    target_base = _resolve_chat_target_base(
        route_id=route_id,
        identity=identity,
        rollout_percent=settings.ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT,
    )
    normalized_conversation_base = settings.CONVERSATION_SERVICE_URL.rstrip("/")
    if target_base.rstrip("/") == normalized_conversation_base:
        ws_base = _conversation_ws_base_url()
    else:
        ws_base = _to_ws_base_url(target_base)
    return f"{ws_base}/{upstream_path}"


@app.websocket("/api/chat/ws")
async def chat_ws_proxy(websocket: WebSocket):
    """
    Customer Chat WebSocket (Modern Target).
    TARGET: Orchestrator Service / Conversation Service
    """
    from starlette.websockets import WebSocketState

    route_id = "chat_ws_customer"
    with tracer.start_as_current_span("ws.proxy", attributes={"agent": "orchestrator"}):
        headers = {}
        _inject_trace_context(headers)
        logger.info(
            f"Chat WebSocket route_id={route_id} legacy_flag=false traceparent={headers.get('traceparent', 'unknown')}"
        )
        _record_ws_session_metric(route_id)
        target_url = _resolve_chat_ws_target(route_id, "api/chat/ws")
        try:
            await websocket_proxy(websocket, target_url)
        except Exception:
            log_telemetry("ws.proxy.failed", trace_id=str(uuid.uuid4()))
            if websocket.client_state == WebSocketState.UNCONNECTED:
                await websocket.accept()
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(
                    {"error": "تعذر فتح جلسة الدردشة حالياً.", "request_id": str(uuid.uuid4())}
                )
                await websocket.close()
```

```python
# app/services/chat/event_protocol.py

def normalize_streaming_event(event: object) -> dict[str, object]:
    """يوحّد حدث البث إلى ChatEventEnvelope مع الإبقاء على السلوك التاريخي عند تعطيل الراية."""
    if not is_unified_chat_event_protocol_enabled():
        if isinstance(event, dict):
            return event
        return {"type": "delta", "payload": {"content": str(event)}}

    if not isinstance(event, dict):
        return build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_DELTA,
            content=str(event),
        )

    raw_type = str(event.get("type", "assistant_delta"))
    payload_value = event.get("payload")
    payload = payload_value if isinstance(payload_value, dict) else {}

    if raw_type in ("status", ChatEventType.STATUS.value):
        status_value = payload.get("status_code")
        status_code = status_value if isinstance(status_value, int) else None
        return build_chat_event_envelope(event_type=ChatEventType.STATUS, status_code=status_code)

    if raw_type in ("error", "assistant_error"):
        details = str(payload.get("details", "")) or str(payload.get("content", ""))
        status_value = payload.get("status_code")
        status_code = status_value if isinstance(status_value, int) else None
        return build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_ERROR,
            details=details,
            status_code=status_code,
        )

    if raw_type == ChatEventType.ASSISTANT_FINAL.value:
        return build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_FINAL,
            content=str(payload.get("content", "")),
        )

    content = str(payload.get("content", "")) if payload else str(event)
    return build_chat_event_envelope(
        event_type=ChatEventType.ASSISTANT_DELTA,
        content=content,
    )
```
