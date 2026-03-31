# E-TAALEEM FORENSIC REPORT

## 1) ROUTER DEAD-END — لماذا "السلام عليكم" ينتهي بصمت

### الإثبات البرمجي
- `SupervisorNode` لا يملك Intent خاصًا للتحية/المحادثة العامة. المنطق الحالي: إذا لم يطابق Admin guard/regex/LLM-admin classification فالقيمة الافتراضية تصبح `"search"`. هذا يحدث صراحة في `intent = "search"` ثم `return {"intent": intent}`.  
- `route_intent` لا يوجّه إلا إلى ثلاث مسارات (`search`, `admin`, `tool`) ولا يوجد أي مسار `conversational_llm` أو `chat_fallback` داخل هذا الـ LangGraph.  
- `add_conditional_edges` على عقدة `supervisor` يربط نفس المفاتيح الثلاثة فقط.

### الجذر المنطقي للعطل
- تحية مثل "السلام عليكم" ليست Admin، فتدخل حتميًا مسار `search`.
- مسار `search` في هذا التصميم مخصص للاسترجاع (QueryAnalyzer → Retriever → Reranker → Synthesizer)، وليس للمحادثة الطبيعية.
- لذلك عند مدخل conversational قصير، النظام يطبّق pipeline استرجاعية بدل محرك محادثة، فلا يوجد fallback حواري صريح في الرسم البياني نفسه.

---

## 2) أثر "؟"/الفراغ في الواجهة عند فشل البث

### نتيجة البحث الحرفي
- بعد فحص الشيفرة التشغيلية ذات الصلة (`customer_chat.py`, `admin.py`, `routes.py`, `chat_streamer.py`) لا يوجد literal مباشر يُرجِع الحرف `"؟"` كرسالة fallback.

### أين تتكوّن حالة الفراغ فعليًا (السبب الحقيقي الأقرب)
1. **تجاهل أي chunk فارغ أثناء التجميع:**
   - في مسار العميل ومسار الأدمن يتم ضم النص فقط عندما يكون `chunk_text` غير فارغ (`and chunk_text`).
   - إذا انتهى stream بدون محتوى نصي فعلي، يبقى `complete_ai_response` فارغًا.
2. **فلاتر streamer تتجاوز الأجزاء الفارغة بالكامل:**
   - كل من `CustomerChatStreamer` و`AdminChatStreamer` يحتوي `if not content: continue`، أي إسقاط صامت لأي جزء فارغ.
3. **تطبيع أحداث الخطأ يغيّر الحقول إلى `details` بدل `content` عند تفعيل envelope الموحد:**
   - `normalize_streaming_event` يحوّل `error/assistant_error` إلى `ASSISTANT_ERROR` بحقل `details`.
   - بينما عدة مستهلكات واجهة تعتمد قراءة `payload.content` لمسارات أخرى؛ في حالات drift قد تظهر رسالة فارغة أو placeholder UI.
4. **مسار LangGraph يُرسل `complete` حتى بعد مسارات صامتة:**
   - في `_stream_chat_langgraph` هناك `final_content = ""` بدايةً، ولا يتم الحفظ إلا إذا كان non-empty (`if final_content.strip()`)، ثم يُرسل `complete` دائمًا.
   - هذا يسمح بإنهاء جلسة دون delta نصي مرئي للمستخدم.

### الجذر المعماري
- ليس هناك توحيد صارم لعقد رسالة الخطأ بين جميع المسارات (بعضها `content`, بعضها `details`) + إسقاط صريح لأي محتوى فارغ في طبقات متعددة.
- النتيجة الظاهرية في UI تصبح "فراغ"، وبعض الواجهات/الخطوط/المكوّنات قد تعرضه كرمز placeholder (يُرى كـ "؟").

---

## 3) GHOST EXAM — لماذا "تمرين" يعيد امتحان 2024 رغم حذف hardcoded fallback

### الإثبات البرمجي
1. **المرشّحات من QueryAnalyzer تكون غالبًا فارغة مع الاستعلامات العامة:**
   - `QueryFilters` افتراضيًا: `year=None`, `subject=""`, `branch=""`, `exercise_num=None`.
   - heuristic fallback لا يملأ شيئًا لـ "تمرين" العام.
2. **InternalRetrieverNode عند غياب النتائج الدقيقة ينتقل إلى بحث دلالي بلا فلاتر (`filters={}`):**
   - هذا يفتح الاسترجاع على كامل المخزن بدون قيد سنة/مادة/شعبة.
3. **استرجاع LlamaIndex لا يضع حدّ تشابه أدنى (min similarity threshold):**
   - `as_retriever(similarity_top_k=limit, filters=llama_filters)` فقط؛ لا يوجد cutoff.
   - بالتالي أي أقرب نتيجة تدخل، حتى لو كانت دلاليًا ضعيفة/عامة.
4. **الترتيب النهائي عند استرجاع SQL/keyword مائل لأحدث سنة:**
   - `ContentSearchQuery` يحدد `ORDER BY i.year DESC NULLS LAST, i.id ASC`.
   - لذا مع استعلام عام أو مطابقات واسعة، الأحدث (مثل 2024) يتقدم طبيعيًا حتى بدون hardcoded `else 2024`.
5. **الـ Relaxed strategy تتعمّد إلغاء الفلاتر الصارمة:**
   - `RelaxedVectorStrategy` يرسل `filters={}` للبحث المتجهي، ثم fetch بدون apply_filters.

### الجذر المعماري
- إزالة fallback الحرفي لا تكفي لأن الانحياز موجود الآن على مستوى **سياسة الاسترجاع**:
  - query عام + عدم عتبة تشابه + توسيع بلا فلاتر + ترتيب SQL تنازلي بالسنة.
- النتيجة النظامية: "تمرين" يلتقط "أفضل/أحدث" عنصر متاح غالبًا من 2024.

---

## الخلاصة التنفيذية
- **الشلل الإداري للتحية**: Router يعامل التحية كـ search لأنه يفتقد intent/conversational node داخل الرسم.
- **أثر "؟"/الفراغ**: ناتج عن إسقاط empty chunks + عدم اتساق حقول الخطأ (`content` مقابل `details`) + إنهاء stream بدون نص مرئي.
- **شبح 2024**: ناتج عن انحياز retrieval policy (relaxed unfiltered semantic + no similarity cutoff + year DESC ordering)، لا عن hardcoded literal.

## الأدلة (Files)
- `microservices/orchestrator_service/src/services/overmind/graph/main.py`
- `app/api/routers/customer_chat.py`
- `app/api/routers/admin.py`
- `app/services/customer/chat_streamer.py`
- `app/services/admin/chat_streamer.py`
- `shared/chat_protocol/event_protocol.py`
- `microservices/orchestrator_service/src/api/routes.py`
- `microservices/orchestrator_service/src/services/overmind/graph/search.py`
- `microservices/research_agent/src/search_engine/retriever.py`
- `microservices/research_agent/src/search_engine/strategies.py`
- `microservices/research_agent/src/content/query_builder.py`
