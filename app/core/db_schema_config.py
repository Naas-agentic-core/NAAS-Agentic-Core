"""تعريفات مخطط قاعدة البيانات المعتمدة للنظام.

توفر هذه الوحدة بيانات المخطط المطلوبة وقوائم الجداول المسموح بها
بهدف تقليل التعقيد في منطق التحقق وضمان وضوح الحدود البنيوية.
"""

from typing import Final, NotRequired, TypedDict

__all__ = [
    "REQUIRED_SCHEMA",
    "_ALLOWED_TABLES",
    "SchemaValidationResult",
    "TableSchemaConfig",
]


class TableSchemaConfig(TypedDict):
    """تمثيل تعريف جدول مع أوامر الإصلاح والفهارس المطلوبة."""

    columns: list[str]
    auto_fix: dict[str, str]
    indexes: dict[str, str]
    index_names: NotRequired[dict[str, str]]
    create_table: NotRequired[str]


class SchemaValidationResult(TypedDict):
    """نتيجة التحقق من المخطط مع تفاصيل العناصر الناقصة أو المُعالجة."""

    status: str
    checked_tables: list[str]
    missing_columns: list[str]
    fixed_columns: list[str]
    missing_indexes: list[str]
    fixed_indexes: list[str]
    errors: list[str]


_ALLOWED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "admin_conversations",
        "admin_messages",
        "audit_log",
        "customer_conversations",
        "customer_messages",
        "permissions",
        "refresh_tokens",
        "role_permissions",
        "roles",
        "user_roles",
        "users",
        "missions",
        "mission_plans",
        "tasks",
        "mission_events",
        "prompt_templates",
        "generated_prompts",
        "knowledge_nodes",
        "knowledge_edges",
        "student_bkt_analytics",
        "tutor_state",
        "bac_exercises",
        "bac_exercise_questions",
        # D-200: مخزن المحتوى الذي تستعلمه `/v1/content/*` — كان مُعرَّفاً في ORM
        # لا يستورده أحد، فلم يُنشئه مسار الإقلاع أبداً (انظر تعليق REQUIRED_SCHEMA).
        "content_items",
        "content_solutions",
        # D-194: سجلّ المراجعة المتباعدة (FSRS) — مُلحَق-فقط فوق BKT.
        "student_review_schedule",
        # D-196: ربط وليّ الأمر بالطالب — برضا الطالب حصراً.
        "guardian_links",
        # D-197: سجلّ أحداث المنتج — مُلحَق-فقط، أساس الاحتفاظ والأفواج.
        "product_events",
        # D-198: القسائم المدفوعة مسبقاً + حقوق الوصول.
        "vouchers",
        "voucher_redemptions",
        "entitlements",
        # D-201: صندوق صادر الإشعارات — المستهلك الحيّ لناقل الأحداث.
        "notification_outbox",
    }
)


REQUIRED_SCHEMA: Final[dict[str, TableSchemaConfig]] = {
    # Protocol V24.0 — جدول تمارين البكالوريا المُهيكَل (Data Engineering Mandate).
    # يحوّل المحتوى التعليمي من نص خام إلى صفوف ذات بيانات وصفية صارمة لتغذية
    # محرّك RAG بدقة دلالية (subject/topic/draw_type/year + parsed_entities JSONB).
    # Protocol V24.1 — جدول الأسئلة الفرعية (Surgical Precision).
    # يفصل التمارين إلى أجزاء دقيقة جداً مع إضافة بحث متجهي (Vector) لكل جزء.
    "bac_exercise_questions": {
        "columns": [
            "id",
            "exercise_id",
            "question_number",
            "question_text",
            "question_type",
            "parsed_entities",
            "embedding",
            "search_vector",
            "created_at",
        ],
        # D-158: نُقلت ALTERs الخاصة بـ tutor_state من هنا (كانت مُفلترة خطأً تحت
        # bac_exercise_questions فلم تُطبَّق أبداً — الجذر الأعمق: أعمدة tutor_state
        # الناقصة على DB قديمة ⇒ كل كتابات record_turn تفشل صامتة). مكانها الصحيح
        # الآن تحت مدخل "tutor_state" أدناه.
        "auto_fix": {},
        "indexes": {
            "exercise_id": 'CREATE INDEX IF NOT EXISTS "ix_bac_exercise_questions_exercise_id" ON "bac_exercise_questions"("exercise_id")',
            "embedding": 'CREATE INDEX IF NOT EXISTS "ix_bac_exercise_questions_embedding" ON "bac_exercise_questions" USING hnsw ("embedding" vector_cosine_ops)',
            "search_vector": 'CREATE INDEX IF NOT EXISTS "ix_bac_exercise_questions_search_vector" ON "bac_exercise_questions" USING GIN ("search_vector")',
            "parsed_entities": 'CREATE INDEX IF NOT EXISTS "ix_bac_exercise_questions_parsed_entities" ON "bac_exercise_questions" USING GIN ("parsed_entities")',
        },
        "index_names": {
            "exercise_id": "ix_bac_exercise_questions_exercise_id",
            "embedding": "ix_bac_exercise_questions_embedding",
            "search_vector": "ix_bac_exercise_questions_search_vector",
            "parsed_entities": "ix_bac_exercise_questions_parsed_entities",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "bac_exercise_questions"('
            '"id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),'
            '"exercise_id" UUID NOT NULL REFERENCES "bac_exercises"("id") ON DELETE CASCADE,'
            '"question_number" VARCHAR(20) NOT NULL,'
            '"question_text" TEXT NOT NULL,'
            '"question_type" VARCHAR(50),'
            "\"parsed_entities\" JSONB NOT NULL DEFAULT '{}',"
            '"embedding" vector(1024),'
            "\"search_vector\" tsvector GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(\"question_text\", ''))) STORED,"
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "bac_exercises": {
        "columns": [
            "id",
            "subject",
            "topic",
            "draw_type",
            "year",
            "session",
            "branch",
            "exam_ref",
            "exercise_number",
            "language",
            "source",
            "content_hash",
            "raw_text",
            "parsed_entities",
            "created_at",
            "updated_at",
        ],
        "auto_fix": {},
        "indexes": {
            "subject": 'CREATE INDEX IF NOT EXISTS "ix_bac_exercises_subject" ON "bac_exercises"("subject")',
            "topic": 'CREATE INDEX IF NOT EXISTS "ix_bac_exercises_topic" ON "bac_exercises"("topic")',
            "year": 'CREATE INDEX IF NOT EXISTS "ix_bac_exercises_year" ON "bac_exercises"("year")',
            "draw_type": 'CREATE INDEX IF NOT EXISTS "ix_bac_exercises_draw_type" ON "bac_exercises"("draw_type")',
            "parsed_entities": 'CREATE INDEX IF NOT EXISTS "ix_bac_exercises_parsed_entities" ON "bac_exercises" USING GIN ("parsed_entities")',
        },
        "index_names": {
            "subject": "ix_bac_exercises_subject",
            "topic": "ix_bac_exercises_topic",
            "year": "ix_bac_exercises_year",
            "draw_type": "ix_bac_exercises_draw_type",
            "parsed_entities": "ix_bac_exercises_parsed_entities",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "bac_exercises"('
            '"id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),'
            '"subject" VARCHAR(80) NOT NULL,'
            '"topic" VARCHAR(120) NOT NULL,'
            '"draw_type" VARCHAR(40),'
            '"year" INTEGER NOT NULL CHECK ("year" BETWEEN 1990 AND 2100),'
            '"session" VARCHAR(60),'
            '"branch" VARCHAR(160),'
            '"exam_ref" VARCHAR(120),'
            '"exercise_number" INTEGER,'
            "\"language\" VARCHAR(8) NOT NULL DEFAULT 'ar',"
            '"source" VARCHAR(255),'
            '"content_hash" VARCHAR(64) NOT NULL UNIQUE,'
            '"raw_text" TEXT NOT NULL,'
            "\"parsed_entities\" JSONB NOT NULL DEFAULT '{}',"
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "student_bkt_analytics": {
        "columns": [
            "id",
            "user_id",
            "session_id",
            "concept_id",
            "cognitive_load_estimate",
            "student_mastery_probability",
            "interaction_count",
            "interaction_timestamp",
            "created_at",
            # D-126: الإتقان الصادق ثنائي القناة (Two-Signal Honest Mastery).
            "durable_mastery",
            "support_level",
            "delay_hours",
            "novel_item",
        ],
        # D-126: أعمدة القناة الدائمة تُضاف تلقائياً على الإقلاع (auto-migration §6.77)
        # على القواعد القائمة — append-only، لا تكسر الصفوف السابقة (افتراضات آمنة).
        "auto_fix": {
            "durable_mastery": (
                'ALTER TABLE "student_bkt_analytics" ADD COLUMN "durable_mastery" '
                "DOUBLE PRECISION NOT NULL DEFAULT 0.0"
            ),
            "support_level": (
                'ALTER TABLE "student_bkt_analytics" ADD COLUMN "support_level" INTEGER'
            ),
            "delay_hours": (
                'ALTER TABLE "student_bkt_analytics" ADD COLUMN "delay_hours" DOUBLE PRECISION'
            ),
            "novel_item": (
                'ALTER TABLE "student_bkt_analytics" ADD COLUMN "novel_item" '
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ),
        },
        "indexes": {
            "user_id": 'CREATE INDEX IF NOT EXISTS "ix_student_bkt_analytics_user_id" ON "student_bkt_analytics"("user_id")',
            "concept_id": 'CREATE INDEX IF NOT EXISTS "ix_student_bkt_analytics_concept_id" ON "student_bkt_analytics"("concept_id")',
            "interaction_timestamp": 'CREATE INDEX IF NOT EXISTS "ix_student_bkt_analytics_interaction_timestamp" ON "student_bkt_analytics"("interaction_timestamp")',
        },
        "index_names": {
            "user_id": "ix_student_bkt_analytics_user_id",
            "concept_id": "ix_student_bkt_analytics_concept_id",
            "interaction_timestamp": "ix_student_bkt_analytics_interaction_timestamp",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "student_bkt_analytics"('
            '"id" SERIAL PRIMARY KEY,'
            '"user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            '"session_id" INTEGER,'
            '"concept_id" VARCHAR(120) NOT NULL,'
            "\"cognitive_load_estimate\" VARCHAR(10) NOT NULL DEFAULT 'medium' "
            "CHECK (\"cognitive_load_estimate\" IN ('low','medium','high')),"
            '"student_mastery_probability" DOUBLE PRECISION NOT NULL DEFAULT 0.0 '
            'CHECK ("student_mastery_probability" >= 0.0 AND "student_mastery_probability" <= 1.0),'
            '"interaction_count" INTEGER NOT NULL DEFAULT 1,'
            '"interaction_timestamp" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            # D-126: القناة الدائمة (durable) + مدخلاتها (append-only).
            '"durable_mastery" DOUBLE PRECISION NOT NULL DEFAULT 0.0 '
            'CHECK ("durable_mastery" >= 0.0 AND "durable_mastery" <= 1.0),'
            '"support_level" INTEGER,'
            '"delay_hours" DOUBLE PRECISION,'
            '"novel_item" BOOLEAN NOT NULL DEFAULT FALSE'
            ")"
        ),
    },
    # D-201: صندوق صادر الإشعارات. `event_id` **فريد** — وهو ما يجعل إعادة تسليم
    # الحدث من الناقل لا تُنتِج إشعاراً ثانياً. الحَكَم قيدٌ في قاعدة البيانات لا فحصٌ
    # في التطبيق (نفس درس D-198: «افحص ثمّ اكتب» نافذة سباق).
    "notification_outbox": {
        "columns": [
            "id",
            "event_id",
            "user_id",
            "channel",
            "template",
            "payload_json",
            "status",
            "created_at",
            "sent_at",
        ],
        "auto_fix": {},
        "indexes": {
            "event_id": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_notification_outbox_event_id" ON "notification_outbox"("event_id")',
            "status": 'CREATE INDEX IF NOT EXISTS "ix_notification_outbox_status" ON "notification_outbox"("status","created_at")',
        },
        "index_names": {
            "event_id": "ix_notification_outbox_event_id",
            "status": "ix_notification_outbox_status",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "notification_outbox"('
            '"id" SERIAL PRIMARY KEY,'
            '"event_id" VARCHAR(64) NOT NULL,'
            '"user_id" INTEGER,'
            "\"channel\" VARCHAR(32) NOT NULL DEFAULT 'in_app',"
            '"template" VARCHAR(64) NOT NULL,'
            '"payload_json" TEXT,'
            "\"status\" VARCHAR(16) NOT NULL DEFAULT 'pending' "
            "CHECK (\"status\" IN ('pending','sent','failed')),"
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"sent_at" TIMESTAMPTZ'
            ")"
        ),
    },
    # D-200: مخزن المحتوى. **عطبٌ كامن حقيقي كُشِف عند توصيل الترتيب:**
    # `app/api/routers/content.py` يستعلم `content_items` في ثلاثة مسارات (والأداة
    # `services/chat/tools/curriculum.py` في رابع)، بينما الجدول لم يكن مُسجَّلاً هنا،
    # ونموذج SQLModel في `app/core/domain/content.py` **لا يستورده أيّ ملفّ** فلا يدخل
    # `SQLModel.metadata` أصلاً. أي أنّ الجدول لم يكن يُنشَأ بأيّ مسار إقلاع: على قاعدة
    # بيانات نظيفة كانت `/v1/content/search` تُرجِع 500. التسجيل هنا هو مسار المخطط
    # الوحيد (شبكة الساندبوكس تحجب منافذ Postgres — CLAUDE.md §0).
    "content_items": {
        "columns": [
            "id",
            "type",
            "title",
            "level",
            "subject",
            "set_name",
            "year",
            "lang",
            "md_content",
            "source_path",
            "sha256",
            "updated_at",
        ],
        "auto_fix": {},
        "indexes": {
            # الاستعلام الحارّ للبحث: تصفية بالحقلين معاً قبل الترتيب الحتمي.
            "subject": 'CREATE INDEX IF NOT EXISTS "ix_content_items_subject_level" ON "content_items"("subject","level")',
            "year": 'CREATE INDEX IF NOT EXISTS "ix_content_items_year" ON "content_items"("year")',
        },
        "index_names": {
            "subject": "ix_content_items_subject_level",
            "year": "ix_content_items_year",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "content_items"('
            '"id" VARCHAR(100) PRIMARY KEY,'
            "\"type\" VARCHAR(50) NOT NULL DEFAULT 'exercise',"
            '"title" TEXT,'
            '"level" VARCHAR(50),'
            '"subject" VARCHAR(100),'
            '"set_name" VARCHAR(100),'
            '"year" INTEGER,'
            "\"lang\" VARCHAR(10) NOT NULL DEFAULT 'ar',"
            '"md_content" TEXT NOT NULL,'
            '"source_path" VARCHAR(255),'
            '"sha256" VARCHAR(64),'
            '"updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    # الحلّ النموذجي منفصلٌ عن التمرين بنيوياً — لأنّ D-113 يمنع تسليمه للطالب، وفصل
    # الجدول يجعل «سلّمنا الحلّ بالخطأ» غير مُمثَّل في استعلام البحث بدل أن يكون
    # مُرشَّحاً يعتمد على انتقاء الأعمدة.
    "content_solutions": {
        "columns": [
            "content_id",
            "solution_md",
            "steps_json",
            "final_answer",
            "verified_by",
            "updated_at",
        ],
        "auto_fix": {},
        "indexes": {},
        "index_names": {},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "content_solutions"('
            '"content_id" VARCHAR(100) PRIMARY KEY,'
            '"solution_md" TEXT NOT NULL,'
            '"steps_json" TEXT,'
            '"final_answer" TEXT,'
            '"verified_by" VARCHAR(100),'
            '"updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    # D-194: سجلّ المراجعة المتباعدة (FSRS) — **مُلحَق-فقط**، بنفس انضباط
    # `student_bkt_analytics`: كل مراجعة صفٌّ جديد، والحالة الحيّة هي أحدث صفّ لكل
    # (user_id, concept_id). لا تحديث في المكان، فتبقى السلسلة الزمنية كاملة للتحليل
    # ولإعادة تدريب معاملات FSRS على بيانات المنصّة نفسها لاحقاً.
    "student_review_schedule": {
        "columns": [
            "id",
            "user_id",
            "concept_id",
            "rating",
            "stability",
            "difficulty",
            "reps",
            "lapses",
            "state",
            "reviewed_at",
            "due_at",
            "interval_days",
            "created_at",
        ],
        "auto_fix": {},
        "indexes": {
            "user_id": 'CREATE INDEX IF NOT EXISTS "ix_student_review_schedule_user_id" ON "student_review_schedule"("user_id")',
            "concept_id": 'CREATE INDEX IF NOT EXISTS "ix_student_review_schedule_concept_id" ON "student_review_schedule"("concept_id")',
            # الاستعلام الحارّ: «ما المستحقّ لهذا الطالب الآن» ⇒ فهرس مركّب.
            "due_at": 'CREATE INDEX IF NOT EXISTS "ix_student_review_schedule_due_at" ON "student_review_schedule"("user_id","due_at")',
        },
        "index_names": {
            "user_id": "ix_student_review_schedule_user_id",
            "concept_id": "ix_student_review_schedule_concept_id",
            "due_at": "ix_student_review_schedule_due_at",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "student_review_schedule"('
            '"id" SERIAL PRIMARY KEY,'
            '"user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            '"concept_id" VARCHAR(120) NOT NULL,'
            '"rating" INTEGER NOT NULL CHECK ("rating" BETWEEN 1 AND 4),'
            '"stability" DOUBLE PRECISION NOT NULL CHECK ("stability" > 0),'
            '"difficulty" DOUBLE PRECISION NOT NULL '
            'CHECK ("difficulty" >= 1.0 AND "difficulty" <= 10.0),'
            '"reps" INTEGER NOT NULL DEFAULT 1,'
            '"lapses" INTEGER NOT NULL DEFAULT 0,'
            "\"state\" VARCHAR(16) NOT NULL DEFAULT 'review' "
            "CHECK (\"state\" IN ('learning','review','relearning')),"
            '"reviewed_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"due_at" TIMESTAMPTZ NOT NULL,'
            '"interval_days" DOUBLE PRECISION NOT NULL,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    # D-198: القسائم المدفوعة مسبقاً. الرمز **مُجزَّأ** (سندٌ لحامله)، والاستبدال الواحد
    # مفروضٌ بقيد فريد على `voucher_redemptions.voucher_id` — لا بفحصٍ في التطبيق، لأنّ
    # «افحص ثمّ اكتب» نافذةُ سباق يعبرها طلبان متزامنان.
    "vouchers": {
        "columns": [
            "id",
            "code_hash",
            "plan",
            "duration_days",
            "status",
            "created_at",
            "expires_at",
        ],
        "auto_fix": {},
        "indexes": {
            "code_hash": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_vouchers_code_hash" ON "vouchers"("code_hash")',
        },
        "index_names": {"code_hash": "ix_vouchers_code_hash"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "vouchers"('
            '"id" SERIAL PRIMARY KEY,'
            '"code_hash" VARCHAR(64) NOT NULL,'
            "\"plan\" VARCHAR(32) NOT NULL DEFAULT 'standard',"
            '"duration_days" INTEGER NOT NULL DEFAULT 30 CHECK ("duration_days" > 0),'
            "\"status\" VARCHAR(16) NOT NULL DEFAULT 'issued' "
            "CHECK (\"status\" IN ('issued','redeemed','void')),"
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"expires_at" TIMESTAMPTZ'
            ")"
        ),
    },
    "voucher_redemptions": {
        "columns": ["id", "voucher_id", "user_id", "redeemed_at"],
        "auto_fix": {},
        "indexes": {
            # القيد الفريد هو الحَكَم: استبدالٌ واحد لكلّ قسيمة، مهما تزامنت الطلبات.
            "voucher_id": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_voucher_redemptions_voucher" ON "voucher_redemptions"("voucher_id")',
            "user_id": 'CREATE INDEX IF NOT EXISTS "ix_voucher_redemptions_user" ON "voucher_redemptions"("user_id")',
        },
        "index_names": {
            "voucher_id": "ix_voucher_redemptions_voucher",
            "user_id": "ix_voucher_redemptions_user",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "voucher_redemptions"('
            '"id" SERIAL PRIMARY KEY,'
            '"voucher_id" INTEGER NOT NULL UNIQUE REFERENCES "vouchers"("id") ON DELETE CASCADE,'
            '"user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            '"redeemed_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "entitlements": {
        "columns": ["id", "user_id", "plan", "source", "granted_at", "expires_at"],
        "auto_fix": {},
        "indexes": {
            "expires_at": 'CREATE INDEX IF NOT EXISTS "ix_entitlements_expires_at" ON "entitlements"("expires_at")',
            "ix_entitlements_user_id_expires_at_id": 'CREATE INDEX IF NOT EXISTS "ix_entitlements_user_id_expires_at_id" ON "entitlements"("user_id","expires_at","id")',
        },
        "index_names": {
            "expires_at": "ix_entitlements_expires_at",
            "ix_entitlements_user_id_expires_at_id": "ix_entitlements_user_id_expires_at_id",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "entitlements"('
            '"id" SERIAL PRIMARY KEY,'
            '"user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            "\"plan\" VARCHAR(32) NOT NULL DEFAULT 'standard',"
            "\"source\" VARCHAR(32) NOT NULL DEFAULT 'voucher',"
            '"granted_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"expires_at" TIMESTAMPTZ NOT NULL'
            ")"
        ),
    },
    # D-197: أحداث المنتج — مُلحَق-فقط. أساس الاحتفاظ والأفواج والقُمع. `user_id` يقبل
    # NULL لأنّ بعض الأحداث تسبق المصادقة. `props` سياق صغير — ممنوع أن يحمل نصّ محادثة.
    "product_events": {
        "columns": [
            "id",
            "user_id",
            "event_name",
            "session_id",
            "props",
            "occurred_at",
        ],
        "auto_fix": {},
        "indexes": {
            "user_id": 'CREATE INDEX IF NOT EXISTS "ix_product_events_user_id" ON "product_events"("user_id")',
            "event_name": 'CREATE INDEX IF NOT EXISTS "ix_product_events_event_name" ON "product_events"("event_name")',
            # الاستعلام الحارّ: أحداثُ نوعٍ ما ضمن نافذة زمنية.
            "occurred_at": 'CREATE INDEX IF NOT EXISTS "ix_product_events_occurred_at" ON "product_events"("event_name","occurred_at")',
        },
        "index_names": {
            "user_id": "ix_product_events_user_id",
            "event_name": "ix_product_events_event_name",
            "occurred_at": "ix_product_events_occurred_at",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "product_events"('
            '"id" SERIAL PRIMARY KEY,'
            '"user_id" INTEGER REFERENCES "users"("id") ON DELETE CASCADE,'
            '"event_name" VARCHAR(64) NOT NULL,'
            '"session_id" INTEGER,'
            '"props" TEXT,'
            '"occurred_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    # D-196: ربط وليّ الأمر بالطالب. **الرضا شرط بنيوي لا سياسة**: الطالب يُولِّد رمزاً
    # ويسلّمه لوليّه، والوليّ يستبدله. لا يوجد مسارٌ يربط حساب قاصر بحساب آخر دون فعلٍ
    # صريح من الطالب نفسه — ولا يوجد عمود يسمح بذلك.
    "guardian_links": {
        "columns": [
            "id",
            "guardian_user_id",
            "student_user_id",
            "link_code",
            "status",
            "created_at",
            "accepted_at",
            "revoked_at",
        ],
        "auto_fix": {},
        "indexes": {
            "guardian_user_id": 'CREATE INDEX IF NOT EXISTS "ix_guardian_links_guardian" ON "guardian_links"("guardian_user_id")',
            "student_user_id": 'CREATE INDEX IF NOT EXISTS "ix_guardian_links_student" ON "guardian_links"("student_user_id")',
            "link_code": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_guardian_links_code" ON "guardian_links"("link_code")',
        },
        "index_names": {
            "guardian_user_id": "ix_guardian_links_guardian",
            "student_user_id": "ix_guardian_links_student",
            "link_code": "ix_guardian_links_code",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "guardian_links"('
            '"id" SERIAL PRIMARY KEY,'
            # فارغ حتى يستبدل الوليُّ الرمز — الرابط يبدأ من الطالب دائماً.
            '"guardian_user_id" INTEGER REFERENCES "users"("id") ON DELETE CASCADE,'
            '"student_user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            '"link_code" VARCHAR(32) NOT NULL,'
            "\"status\" VARCHAR(16) NOT NULL DEFAULT 'pending' "
            "CHECK (\"status\" IN ('pending','active','revoked')),"
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"accepted_at" TIMESTAMPTZ,'
            '"revoked_at" TIMESTAMPTZ'
            ")"
        ),
    },
    # D-142 (Phase 2): حالة جلسة التدريس الدائمة — صف حيّ واحد لكل محادثة (upsert).
    # يُنشأ تلقائياً على الإقلاع (auto-create §6.77) على أي قاعدة نظيفة (SQLite/Supabase).
    "tutor_state": {
        "columns": [
            "id",
            "conversation_id",
            "user_id",
            "active_concept",
            "active_misconception",
            "kc_progress",
            "ability_snapshot",
            "learning_stage",
            "representation_used",
            "interventions_used",
            "mastery_score",
            "dead_ends",
            "frustration_score",
            "next_best_action",
            "socratic_count_by_concept",
            "last_step_emitted",
            "turn_count",
            "updated_at",
            "created_at",
        ],
        "indexes": {
            "conversation_id": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_tutor_state_conversation_id" ON "tutor_state"("conversation_id")',
            "user_id": 'CREATE INDEX IF NOT EXISTS "ix_tutor_state_user_id" ON "tutor_state"("user_id")',
        },
        "index_names": {
            "conversation_id": "ix_tutor_state_conversation_id",
            "user_id": "ix_tutor_state_user_id",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "tutor_state"('
            '"id" SERIAL PRIMARY KEY,'
            '"conversation_id" INTEGER NOT NULL UNIQUE,'
            '"user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            "\"active_concept\" VARCHAR(120) NOT NULL DEFAULT '',"
            "\"active_misconception\" VARCHAR(120) NOT NULL DEFAULT '',"
            "\"kc_progress\" TEXT NOT NULL DEFAULT '{}',"
            '"ability_snapshot" DOUBLE PRECISION NOT NULL DEFAULT 0.0,'
            "\"learning_stage\" VARCHAR(50) NOT NULL DEFAULT 'definition',"
            "\"representation_used\" VARCHAR(50) NOT NULL DEFAULT 'text',"
            "\"interventions_used\" TEXT NOT NULL DEFAULT '[]',"
            '"mastery_score" DOUBLE PRECISION NOT NULL DEFAULT 0.0,'
            "\"dead_ends\" TEXT NOT NULL DEFAULT '[]',"
            '"frustration_score" DOUBLE PRECISION NOT NULL DEFAULT 0.0,'
            "\"next_best_action\" VARCHAR(120) NOT NULL DEFAULT '',"
            "\"socratic_count_by_concept\" TEXT NOT NULL DEFAULT '{}',"
            "\"last_step_emitted\" TEXT NOT NULL DEFAULT '',"
            '"turn_count" INTEGER NOT NULL DEFAULT 0,'
            '"updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
        # D-158: auto_fix في مكانه الصحيح أخيراً. الأعمدة أدناه كانت تُنشأ فقط عبر
        # CREATE TABLE IF NOT EXISTS (no-op على جدول D-142 القائم) وALTERs كانت مُفلترة
        # تحت الجدول الخطأ ⇒ كل كتابات tutor_state تفشل صامتة على DB قديمة (السبب الأعمق
        # لِـ ISS-124). تُطبَّق فقط للأعمدة المرصودة ناقصة (idempotent). kc_progress مُدرج
        # دفاعياً (موجود أصلاً على DB الحالية فلا يُطبَّق).
        "auto_fix": {
            "kc_progress": 'ALTER TABLE "tutor_state" ADD COLUMN "kc_progress" TEXT NOT NULL DEFAULT \'{}\'',
            "learning_stage": 'ALTER TABLE "tutor_state" ADD COLUMN "learning_stage" VARCHAR(50) NOT NULL DEFAULT \'definition\'',
            "representation_used": 'ALTER TABLE "tutor_state" ADD COLUMN "representation_used" VARCHAR(50) NOT NULL DEFAULT \'text\'',
            "interventions_used": 'ALTER TABLE "tutor_state" ADD COLUMN "interventions_used" TEXT NOT NULL DEFAULT \'[]\'',
            "mastery_score": 'ALTER TABLE "tutor_state" ADD COLUMN "mastery_score" DOUBLE PRECISION NOT NULL DEFAULT 0.0',
            "dead_ends": 'ALTER TABLE "tutor_state" ADD COLUMN "dead_ends" TEXT NOT NULL DEFAULT \'[]\'',
            "frustration_score": 'ALTER TABLE "tutor_state" ADD COLUMN "frustration_score" DOUBLE PRECISION NOT NULL DEFAULT 0.0',
            "next_best_action": 'ALTER TABLE "tutor_state" ADD COLUMN "next_best_action" VARCHAR(120) NOT NULL DEFAULT \'\'',
        },
    },
    "admin_conversations": {
        "columns": [
            "id",
            "title",
            "user_id",
            "conversation_type",
            "linked_mission_id",
            "created_at",
        ],
        "auto_fix": {
            "linked_mission_id": 'ALTER TABLE "admin_conversations" ADD COLUMN "linked_mission_id" INTEGER'
        },
        "indexes": {
            "linked_mission_id": 'CREATE INDEX IF NOT EXISTS "ix_admin_conversations_linked_mission_id" ON "admin_conversations"("linked_mission_id")'
        },
        "index_names": {"linked_mission_id": "ix_admin_conversations_linked_mission_id"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "admin_conversations"('
            '"id" SERIAL PRIMARY KEY,'
            '"title" VARCHAR(500) NOT NULL,'
            '"user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            "\"conversation_type\" VARCHAR(50) DEFAULT 'general',"
            '"linked_mission_id" INTEGER,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    # D-WS-PROXY-004 follow-up (ISS-102, 2026-05-31): admin_messages كان مفقوداً
    # من REQUIRED_SCHEMA و _ALLOWED_TABLES → على أي قاعدة بيانات جديدة (SQLite أو
    # Supabase نظيف) كانت دردشة الإدمن تفشل بـ "no such table: admin_messages"
    # عند حفظ رسالة المستخدم. مرآة customer_messages لكن بـ FK إلى
    # admin_conversations وبلا policy_flags (مطابقة ORM app/core/domain/chat.py).
    "admin_messages": {
        "columns": [
            "id",
            "conversation_id",
            "role",
            "content",
            "ui_component",
            "created_at",
        ],
        "auto_fix": {
            # ISS-106 (D-WS-CARD-PERSIST-001): generative-UI card JSON (admin parity).
            "ui_component": 'ALTER TABLE "admin_messages" ADD COLUMN "ui_component" TEXT',
        },
        "indexes": {
            "conversation_id": 'CREATE INDEX IF NOT EXISTS "ix_admin_messages_conversation_id" ON "admin_messages"("conversation_id")'
        },
        "index_names": {"conversation_id": "ix_admin_messages_conversation_id"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "admin_messages"('
            '"id" SERIAL PRIMARY KEY,'
            '"conversation_id" INTEGER NOT NULL REFERENCES "admin_conversations"("id") ON DELETE CASCADE,'
            '"role" VARCHAR(50) NOT NULL,'
            '"content" TEXT NOT NULL,'
            '"ui_component" TEXT,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "customer_conversations": {
        "columns": [
            "id",
            "title",
            "user_id",
            "created_at",
        ],
        "auto_fix": {},
        "indexes": {
            "user_id": 'CREATE INDEX IF NOT EXISTS "ix_customer_conversations_user_id" ON "customer_conversations"("user_id")'
        },
        "index_names": {"user_id": "ix_customer_conversations_user_id"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "customer_conversations"('
            '"id" SERIAL PRIMARY KEY,'
            '"title" VARCHAR(500) NOT NULL,'
            '"user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "customer_messages": {
        "columns": [
            "id",
            "conversation_id",
            "role",
            "content",
            "policy_flags",
            "ui_component",
            "created_at",
        ],
        "auto_fix": {
            # ISS-106 (D-WS-CARD-PERSIST-001): generative-UI card JSON, so cards
            # survive logout/login. ALTER adds the column to existing Supabase tables.
            "ui_component": 'ALTER TABLE "customer_messages" ADD COLUMN "ui_component" TEXT',
        },
        "indexes": {
            "conversation_id": 'CREATE INDEX IF NOT EXISTS "ix_customer_messages_conversation_id" ON "customer_messages"("conversation_id")'
        },
        "index_names": {"conversation_id": "ix_customer_messages_conversation_id"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "customer_messages"('
            '"id" SERIAL PRIMARY KEY,'
            '"conversation_id" INTEGER NOT NULL REFERENCES "customer_conversations"("id") ON DELETE CASCADE,'
            '"role" VARCHAR(50) NOT NULL,'
            '"content" TEXT NOT NULL,'
            '"policy_flags" TEXT,'
            '"ui_component" TEXT,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "users": {
        "columns": [
            "id",
            "external_id",
            "full_name",
            "email",
            "password_hash",
            "is_admin",
            "is_active",
            "status",
            "created_at",
            "updated_at",
        ],
        "auto_fix": {
            "external_id": 'ALTER TABLE "users" ADD COLUMN "external_id" VARCHAR(36)',
            "is_active": 'ALTER TABLE "users" ADD COLUMN "is_active" BOOLEAN NOT NULL DEFAULT TRUE',
            "status": 'ALTER TABLE "users" ADD COLUMN "status" VARCHAR(50) NOT NULL DEFAULT \'active\'',
        },
        "indexes": {
            "external_id": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_users_external_id" ON "users"("external_id")'
        },
        "index_names": {"external_id": "ix_users_external_id"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "users"('
            '"id" SERIAL PRIMARY KEY,'
            '"external_id" VARCHAR(36) UNIQUE,'
            '"full_name" VARCHAR(150) NOT NULL,'
            '"email" VARCHAR(150) NOT NULL UNIQUE,'
            '"password_hash" VARCHAR(256),'
            '"is_admin" BOOLEAN DEFAULT FALSE,'
            '"is_active" BOOLEAN DEFAULT TRUE,'
            "\"status\" VARCHAR(50) DEFAULT 'active',"
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "roles": {
        "columns": [
            "id",
            "name",
            "description",
            "created_at",
            "updated_at",
        ],
        "auto_fix": {},
        "indexes": {
            "name": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_roles_name" ON "roles"("name")',
        },
        "index_names": {"name": "ix_roles_name"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "roles"('
            '"id" SERIAL PRIMARY KEY,'
            '"name" VARCHAR(100) NOT NULL UNIQUE,'
            '"description" VARCHAR(255),'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "permissions": {
        "columns": [
            "id",
            "name",
            "description",
            "created_at",
            "updated_at",
        ],
        "auto_fix": {},
        "indexes": {
            "name": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_permissions_name" ON "permissions"("name")',
        },
        "index_names": {"name": "ix_permissions_name"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "permissions"('
            '"id" SERIAL PRIMARY KEY,'
            '"name" VARCHAR(100) NOT NULL UNIQUE,'
            '"description" VARCHAR(255),'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "user_roles": {
        "columns": ["user_id", "role_id", "created_at"],
        "auto_fix": {},
        "indexes": {
            "user_id": 'CREATE INDEX IF NOT EXISTS "ix_user_roles_user_id" ON "user_roles"("user_id")',
            "role_id": 'CREATE INDEX IF NOT EXISTS "ix_user_roles_role_id" ON "user_roles"("role_id")',
        },
        "index_names": {
            "user_id": "ix_user_roles_user_id",
            "role_id": "ix_user_roles_role_id",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "user_roles"('
            '"user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            '"role_id" INTEGER NOT NULL REFERENCES "roles"("id") ON DELETE CASCADE,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            'PRIMARY KEY ("user_id", "role_id")'
            ")"
        ),
    },
    "role_permissions": {
        "columns": ["role_id", "permission_id", "created_at"],
        "auto_fix": {},
        "indexes": {
            "role_id": 'CREATE INDEX IF NOT EXISTS "ix_role_permissions_role_id" ON "role_permissions"("role_id")',
            "permission_id": 'CREATE INDEX IF NOT EXISTS "ix_role_permissions_permission_id" ON "role_permissions"("permission_id")',
        },
        "index_names": {
            "role_id": "ix_role_permissions_role_id",
            "permission_id": "ix_role_permissions_permission_id",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "role_permissions"('
            '"role_id" INTEGER NOT NULL REFERENCES "roles"("id") ON DELETE CASCADE,'
            '"permission_id" INTEGER NOT NULL REFERENCES "permissions"("id") ON DELETE CASCADE,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            'PRIMARY KEY ("role_id", "permission_id")'
            ")"
        ),
    },
    "refresh_tokens": {
        "columns": [
            "id",
            "token_id",
            "family_id",
            "user_id",
            "hashed_token",
            "expires_at",
            "revoked_at",
            "replaced_by_token_id",
            "created_ip",
            "user_agent",
            "created_at",
        ],
        "auto_fix": {
            "family_id": 'ALTER TABLE "refresh_tokens" ADD COLUMN "family_id" VARCHAR(36) NOT NULL DEFAULT \'unknown\'',
            "replaced_by_token_id": 'ALTER TABLE "refresh_tokens" ADD COLUMN "replaced_by_token_id" VARCHAR(36)',
            "created_ip": 'ALTER TABLE "refresh_tokens" ADD COLUMN "created_ip" VARCHAR(64)',
            "user_agent": 'ALTER TABLE "refresh_tokens" ADD COLUMN "user_agent" VARCHAR(255)',
        },
        "indexes": {
            "user_id": 'CREATE INDEX IF NOT EXISTS "ix_refresh_tokens_user_id" ON "refresh_tokens"("user_id")',
            "expires_at": 'CREATE INDEX IF NOT EXISTS "ix_refresh_tokens_expires_at" ON "refresh_tokens"("expires_at")',
            "token_id": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_refresh_tokens_token_id" ON "refresh_tokens"("token_id")',
            "family_id": 'CREATE INDEX IF NOT EXISTS "ix_refresh_tokens_family_id" ON "refresh_tokens"("family_id")',
            "replaced_by_token_id": 'CREATE INDEX IF NOT EXISTS "ix_refresh_tokens_replaced_by_token_id" ON "refresh_tokens"("replaced_by_token_id")',
        },
        "index_names": {
            "user_id": "ix_refresh_tokens_user_id",
            "expires_at": "ix_refresh_tokens_expires_at",
            "token_id": "ix_refresh_tokens_token_id",
            "family_id": "ix_refresh_tokens_family_id",
            "replaced_by_token_id": "ix_refresh_tokens_replaced_by_token_id",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "refresh_tokens"('
            '"id" SERIAL PRIMARY KEY,'
            '"token_id" VARCHAR(36) NOT NULL UNIQUE,'
            '"family_id" VARCHAR(36) NOT NULL,'
            '"user_id" INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,'
            '"hashed_token" VARCHAR(255) NOT NULL,'
            '"expires_at" TIMESTAMPTZ NOT NULL,'
            '"revoked_at" TIMESTAMPTZ,'
            '"replaced_by_token_id" VARCHAR(36),'
            '"created_ip" VARCHAR(64),'
            '"user_agent" VARCHAR(255),'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "audit_log": {
        "columns": [
            "id",
            "actor_user_id",
            "action",
            "target_type",
            "target_id",
            "metadata",
            "ip",
            "user_agent",
            "created_at",
        ],
        "auto_fix": {},
        "indexes": {
            "actor_user_id": 'CREATE INDEX IF NOT EXISTS "ix_audit_log_actor_user_id" ON "audit_log"("actor_user_id")',
            "created_at": 'CREATE INDEX IF NOT EXISTS "ix_audit_log_created_at" ON "audit_log"("created_at")',
        },
        "index_names": {
            "actor_user_id": "ix_audit_log_actor_user_id",
            "created_at": "ix_audit_log_created_at",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "audit_log"('
            '"id" SERIAL PRIMARY KEY,'
            '"actor_user_id" INTEGER REFERENCES "users"("id") ON DELETE SET NULL,'
            '"action" VARCHAR(150) NOT NULL,'
            '"target_type" VARCHAR(100) NOT NULL,'
            '"target_id" VARCHAR(150),'
            "\"metadata\" JSON NOT NULL DEFAULT '{}',"
            '"ip" VARCHAR(64),'
            '"user_agent" VARCHAR(255),'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "missions": {
        "columns": [
            "id",
            "objective",
            "status",
            "initiator_id",
            "active_plan_id",
            "idempotency_key",
            "locked",
            "result_summary",
            "total_cost_usd",
            "adaptive_cycles",
            "created_at",
            "updated_at",
        ],
        "auto_fix": {
            "idempotency_key": 'ALTER TABLE "missions" ADD COLUMN "idempotency_key" VARCHAR(128)',
            "locked": 'ALTER TABLE "missions" ADD COLUMN "locked" BOOLEAN DEFAULT FALSE',
            "result_summary": 'ALTER TABLE "missions" ADD COLUMN "result_summary" TEXT',
            "total_cost_usd": 'ALTER TABLE "missions" ADD COLUMN "total_cost_usd" FLOAT',
            "adaptive_cycles": 'ALTER TABLE "missions" ADD COLUMN "adaptive_cycles" INTEGER DEFAULT 0',
        },
        "indexes": {
            "initiator_id": 'CREATE INDEX IF NOT EXISTS "ix_missions_initiator_id" ON "missions"("initiator_id")',
            "idempotency_key": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_missions_idempotency_key" ON "missions"("idempotency_key")',
        },
        "index_names": {
            "initiator_id": "ix_missions_initiator_id",
            "idempotency_key": "ix_missions_idempotency_key",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "missions"('
            '"id" SERIAL PRIMARY KEY,'
            '"objective" TEXT,'
            "\"status\" VARCHAR(50) DEFAULT 'pending',"
            '"initiator_id" INTEGER NOT NULL REFERENCES "users"("id"),'
            '"active_plan_id" INTEGER,'
            '"idempotency_key" VARCHAR(128) UNIQUE,'
            '"locked" BOOLEAN DEFAULT FALSE,'
            '"result_summary" TEXT,'
            '"total_cost_usd" FLOAT,'
            '"adaptive_cycles" INTEGER DEFAULT 0,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "mission_plans": {
        "columns": [
            "id",
            "mission_id",
            "version",
            "planner_name",
            "status",
            "score",
            "rationale",
            "raw_json",
            "stats_json",
            "warnings_json",
            "content_hash",
            "created_at",
        ],
        "auto_fix": {},
        "indexes": {
            "mission_id": 'CREATE INDEX IF NOT EXISTS "ix_mission_plans_mission_id" ON "mission_plans"("mission_id")'
        },
        "index_names": {"mission_id": "ix_mission_plans_mission_id"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "mission_plans"('
            '"id" SERIAL PRIMARY KEY,'
            '"mission_id" INTEGER NOT NULL REFERENCES "missions"("id"),'
            '"version" INTEGER DEFAULT 1,'
            '"planner_name" VARCHAR(100) NOT NULL,'
            "\"status\" VARCHAR(50) DEFAULT 'draft',"
            '"score" FLOAT DEFAULT 0.0,'
            '"rationale" TEXT,'
            '"raw_json" TEXT,'
            '"stats_json" TEXT,'
            '"warnings_json" TEXT,'
            '"content_hash" VARCHAR(64),'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "tasks": {
        "columns": [
            "id",
            "mission_id",
            "plan_id",
            "task_key",
            "description",
            "tool_name",
            "tool_args_json",
            "status",
            "attempt_count",
            "max_attempts",
            "priority",
            "risk_level",
            "criticality",
            "depends_on_json",
            "result_text",
            "result_meta_json",
            "error_text",
            "started_at",
            "finished_at",
            "next_retry_at",
            "duration_ms",
            "created_at",
            "updated_at",
        ],
        "auto_fix": {},
        "indexes": {
            "mission_id": 'CREATE INDEX IF NOT EXISTS "ix_tasks_mission_id" ON "tasks"("mission_id")',
            "plan_id": 'CREATE INDEX IF NOT EXISTS "ix_tasks_plan_id" ON "tasks"("plan_id")',
        },
        "index_names": {
            "mission_id": "ix_tasks_mission_id",
            "plan_id": "ix_tasks_plan_id",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "tasks"('
            '"id" SERIAL PRIMARY KEY,'
            '"mission_id" INTEGER NOT NULL REFERENCES "missions"("id"),'
            '"plan_id" INTEGER REFERENCES "mission_plans"("id"),'
            '"task_key" VARCHAR(50) NOT NULL,'
            '"description" TEXT,'
            '"tool_name" VARCHAR(100),'
            '"tool_args_json" TEXT,'
            "\"status\" VARCHAR(50) DEFAULT 'pending',"
            '"attempt_count" INTEGER DEFAULT 0,'
            '"max_attempts" INTEGER DEFAULT 3,'
            '"priority" INTEGER DEFAULT 0,'
            '"risk_level" VARCHAR(50),'
            '"criticality" VARCHAR(50),'
            '"depends_on_json" TEXT,'
            '"result_text" TEXT,'
            '"result_meta_json" TEXT,'
            '"error_text" TEXT,'
            '"started_at" TIMESTAMPTZ,'
            '"finished_at" TIMESTAMPTZ,'
            '"next_retry_at" TIMESTAMPTZ,'
            '"duration_ms" INTEGER DEFAULT 0,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '"updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "mission_events": {
        "columns": ["id", "mission_id", "event_type", "payload_json", "created_at"],
        "auto_fix": {"payload_json": 'ALTER TABLE "mission_events" ADD COLUMN "payload_json" TEXT'},
        "indexes": {
            "mission_id": 'CREATE INDEX IF NOT EXISTS "ix_mission_events_mission_id" ON "mission_events"("mission_id")'
        },
        "index_names": {"mission_id": "ix_mission_events_mission_id"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "mission_events"('
            '"id" SERIAL PRIMARY KEY,'
            '"mission_id" INTEGER NOT NULL REFERENCES "missions"("id"),'
            '"event_type" VARCHAR(50) NOT NULL,'
            '"payload_json" TEXT,'
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "prompt_templates": {
        "columns": ["id", "name", "template"],
        "auto_fix": {
            "template": 'ALTER TABLE "prompt_templates" ADD COLUMN "template" TEXT NOT NULL DEFAULT \'\''
        },
        "indexes": {
            "name": 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_prompt_templates_name" ON "prompt_templates"("name")'
        },
        "index_names": {"name": "ix_prompt_templates_name"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "prompt_templates"('
            '"id" SERIAL PRIMARY KEY,'
            '"name" VARCHAR(255) NOT NULL UNIQUE,'
            '"template" TEXT NOT NULL'
            ")"
        ),
    },
    "generated_prompts": {
        "columns": ["id", "prompt", "template_id"],
        "auto_fix": {
            "prompt": 'ALTER TABLE "generated_prompts" ADD COLUMN "prompt" TEXT NOT NULL DEFAULT \'\''
        },
        "indexes": {
            "template_id": 'CREATE INDEX IF NOT EXISTS "ix_generated_prompts_template_id" ON "generated_prompts"("template_id")'
        },
        "index_names": {"template_id": "ix_generated_prompts_template_id"},
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "generated_prompts"('
            '"id" SERIAL PRIMARY KEY,'
            '"prompt" TEXT NOT NULL,'
            '"template_id" INTEGER NOT NULL REFERENCES "prompt_templates"("id")'
            ")"
        ),
    },
    "knowledge_nodes": {
        "columns": [
            "id",
            "label",
            "name",
            "content",
            "embedding",
            "search_vector",
            "metadata",
            "created_at",
        ],
        "auto_fix": {
            "embedding": 'ALTER TABLE "knowledge_nodes" ALTER COLUMN "embedding" TYPE vector(1024)',
            "search_vector": 'ALTER TABLE "knowledge_nodes" ADD COLUMN "search_vector" tsvector GENERATED ALWAYS AS (to_tsvector(\'simple\', "name" || \' \' || COALESCE("content", \'\'))) STORED',
        },
        "indexes": {
            "embedding": 'CREATE INDEX IF NOT EXISTS "ix_knowledge_nodes_embedding" ON "knowledge_nodes" USING hnsw ("embedding" vector_cosine_ops)',
            "name": 'CREATE INDEX IF NOT EXISTS "ix_knowledge_nodes_name" ON "knowledge_nodes"("name")',
            "search_vector": 'CREATE INDEX IF NOT EXISTS "ix_knowledge_nodes_search_vector" ON "knowledge_nodes" USING GIN ("search_vector")',
        },
        "index_names": {
            "embedding": "ix_knowledge_nodes_embedding",
            "name": "ix_knowledge_nodes_name",
            "search_vector": "ix_knowledge_nodes_search_vector",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "knowledge_nodes"('
            '"id" UUID PRIMARY KEY,'
            '"label" VARCHAR(50),'
            '"name" VARCHAR(255) NOT NULL,'
            '"content" TEXT,'
            '"embedding" vector(1024),'
            "\"search_vector\" tsvector GENERATED ALWAYS AS (to_tsvector('simple', \"name\" || ' ' || COALESCE(\"content\", ''))) STORED,"
            "\"metadata\" JSONB DEFAULT '{}',"
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
    "knowledge_edges": {
        "columns": [
            "id",
            "source_id",
            "target_id",
            "relation",
            "properties",
            "created_at",
        ],
        "auto_fix": {},
        "indexes": {
            "source_id": 'CREATE INDEX IF NOT EXISTS "ix_knowledge_edges_source_id" ON "knowledge_edges"("source_id")',
            "target_id": 'CREATE INDEX IF NOT EXISTS "ix_knowledge_edges_target_id" ON "knowledge_edges"("target_id")',
        },
        "index_names": {
            "source_id": "ix_knowledge_edges_source_id",
            "target_id": "ix_knowledge_edges_target_id",
        },
        "create_table": (
            'CREATE TABLE IF NOT EXISTS "knowledge_edges"('
            '"id" UUID PRIMARY KEY,'
            '"source_id" UUID NOT NULL REFERENCES "knowledge_nodes"("id") ON DELETE CASCADE,'
            '"target_id" UUID NOT NULL REFERENCES "knowledge_nodes"("id") ON DELETE CASCADE,'
            '"relation" VARCHAR(50) NOT NULL,'
            "\"properties\" JSONB DEFAULT '{}',"
            '"created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ")"
        ),
    },
}
