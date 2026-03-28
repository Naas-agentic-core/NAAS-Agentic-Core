"""
واجهات Protocol لمكونات MCP - تطبيق مبدأ Dependency Inversion.
===============================================================

يوفر واجهات مجردة لـ:
- IProjectKnowledge: معرفة المشروع
- IResourceFetcher: جلب الموارد
- IToolHandler: معالج الأدوات
"""

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class IProjectKnowledge(Protocol):
    """
    واجهة للحصول على معرفة المشروع.

    تتيح استبدال التنفيذ الحقيقي بـ mocks للاختبارات.
    """

    async def get_complete_knowledge(self) -> dict[str, object]:
        """الحصول على المعرفة الكاملة عن المشروع."""
        ...

    async def get_database_info(self) -> dict[str, object]:
        """الحصول على معلومات قاعدة البيانات."""
        ...

    def get_environment_info(self) -> dict[str, object]:
        """الحصول على معلومات البيئة."""
        ...


@runtime_checkable
class IResourceFetcher(Protocol):
    """
    واجهة لجلب محتوى مورد معين (Strategy Pattern).

    كل مورد له fetcher خاص به يطبق هذه الواجهة.
    """

    @property
    def uri(self) -> str:
        """معرف المورد الذي يتعامل معه هذا الـ fetcher."""
        ...

    async def fetch(self, project_root: Path) -> dict[str, object]:
        """جلب محتوى المورد."""
        ...


@runtime_checkable
class IToolExecutor(Protocol):
    """
    واجهة لتنفيذ أداة MCP.
    """

    async def execute(self, arguments: dict[str, object]) -> dict[str, object]:
        """تنفيذ الأداة بالمعاملات المحددة."""
        ...


@runtime_checkable
class IIntegrationService(Protocol):
    """
    واجهة عامة للتكاملات الخارجية.
    """

    def get_status(self) -> dict[str, object]:
        """الحصول على حالة التكامل."""
        ...


# ============== Resource Fetchers الملموسة ==============


class StructureFetcher:
    """جلب بنية المشروع."""

    uri = "project://structure"

    async def fetch(self, project_root: Path) -> dict[str, object]:
        return {"error": "Service moved to orchestrator_service"}


class MicroservicesFetcher:
    """جلب معلومات الخدمات المصغرة."""

    uri = "project://microservices"

    async def fetch(self, project_root: Path) -> dict[str, object]:
        return {"error": "Service moved to orchestrator_service"}


class DatabaseFetcher:
    """جلب معلومات قاعدة البيانات."""

    uri = "project://database"

    def __init__(self, knowledge: IProjectKnowledge | None = None):
        self._knowledge = knowledge

    async def fetch(self, project_root: Path) -> dict[str, object]:
        return {"error": "Service moved to orchestrator_service"}


class EnvironmentFetcher:
    """جلب معلومات البيئة."""

    uri = "project://environment"

    def __init__(self, knowledge: IProjectKnowledge | None = None):
        self._knowledge = knowledge

    async def fetch(self, project_root: Path) -> dict[str, object]:
        return {"error": "Service moved to orchestrator_service"}


class TechnologiesFetcher:
    """جلب معلومات التقنيات المستخدمة."""

    uri = "project://technologies"

    async def fetch(self, project_root: Path) -> dict[str, object]:
        return {
            "ai_frameworks": [
                {
                    "name": "LangGraph",
                    "status": "✅ نشط",
                    "location": "microservices/orchestrator_service/src/services/overmind/langgraph/",
                    "description": "محرك الوكلاء المتعددين باستخدام الرسوم البيانية",
                },
                {
                    "name": "LlamaIndex",
                    "status": "✅ نشط",
                    "location": "microservices/research_agent/src/search_engine/",
                    "description": "البحث الدلالي واسترجاع المعلومات",
                },
                {
                    "name": "DSPy",
                    "status": "✅ نشط",
                    "location": "microservices/planning_agent/",
                    "description": "البرمجة التصريحية للـ LLMs",
                },
                {
                    "name": "Reranker",
                    "status": "✅ نشط",
                    "location": "microservices/research_agent/src/search_engine/reranker.py",
                    "description": "إعادة ترتيب نتائج البحث بنموذج BAAI/bge-reranker",
                },
                {
                    "name": "Kagent",
                    "status": "✅ نشط",
                    "location": "app/services/kagent/",
                    "description": "شبكة الوكلاء للتوجيه والتنفيذ",
                },
                {
                    "name": "MCP Server",
                    "status": "✅ نشط",
                    "location": "app/services/mcp/",
                    "description": "بروتوكول السياق الموحد للأدوات والموارد",
                },
            ],
            "genius_services": [
                {
                    "name": "Socratic Tutor",
                    "status": "✅ نشط",
                    "location": "app/services/chat/agents/socratic_tutor.py",
                    "description": "المعلم السقراطي - يرشد بالأسئلة بدلاً من الإجابات",
                },
                {
                    "name": "Adaptive Learning",
                    "status": "✅ نشط",
                    "location": "app/services/learning/",
                    "description": "التعلم التكيفي - يتكيف مع مستوى الطالب",
                },
                {
                    "name": "Self-Healing Agent",
                    "status": "✅ نشط",
                    "location": "microservices/orchestrator_service/src/services/overmind/agents/self_healing.py",
                    "description": "الوكيل ذاتي الإصلاح - يتعلم من أخطائه",
                },
                {
                    "name": "Knowledge Graph",
                    "status": "✅ نشط",
                    "location": "app/services/knowledge/",
                    "description": "الرسم البياني للمفاهيم - يربط المفاهيم التعليمية",
                },
                {
                    "name": "Predictive Analytics",
                    "status": "✅ نشط",
                    "location": "app/services/analytics/",
                    "description": "التحليل التنبؤي - يتنبأ بنقاط الضعف",
                },
                {
                    "name": "Multi-Modal Vision",
                    "status": "✅ نشط",
                    "location": "app/services/vision/",
                    "description": "معالجة الوسائط المتعددة - يفهم الصور والرسوم",
                },
                {
                    "name": "Collaborative Learning",
                    "status": "✅ نشط",
                    "location": "app/services/collaboration/",
                    "description": "التعلم التعاوني - جلسات دراسة جماعية",
                },
            ],
            "backend": [
                {"name": "FastAPI", "purpose": "إطار العمل الرئيسي"},
                {"name": "SQLAlchemy", "purpose": "ORM غير متزامن"},
                {"name": "Pydantic v2", "purpose": "التحقق من البيانات"},
                {"name": "PostgreSQL", "purpose": "قاعدة البيانات"},
            ],
        }


class StatsFetcher:
    """جلب إحصائيات سريعة عن المشروع."""

    uri = "project://stats"

    async def fetch(self, project_root: Path) -> dict[str, object]:
        return {"error": "Service moved to orchestrator_service"}

        return {
            "summary": {
                "total_python_files": 0,
                "total_functions": 0,
                "total_classes": 0,
                "total_lines": 0,
                "total_microservices": 0,
            },
            "by_directory": structure.get("by_directory", {}),
            "microservices": microservices.get("services_names", []),
        }


# ============== Genius Services Fetchers ==============


class LearningFetcher:
    """جلب معلومات خدمات التعلم."""

    uri = "genius://learning"

    async def fetch(self, project_root: Path) -> dict[str, object]:
        try:
            from app.services.mcp.integrations import MCPIntegrations

            integrations = MCPIntegrations(project_root)
            return integrations.get_learning_status()
        except Exception as e:
            return {"status": "error", "error": str(e)}


class KnowledgeFetcher:
    """جلب معلومات الرسم البياني للمفاهيم."""

    uri = "genius://knowledge"

    async def fetch(self, project_root: Path) -> dict[str, object]:
        try:
            from app.services.mcp.integrations import MCPIntegrations

            integrations = MCPIntegrations(project_root)
            return integrations.get_knowledge_status()
        except Exception as e:
            return {"status": "error", "error": str(e)}


class AnalyticsFetcher:
    """جلب معلومات خدمات التحليل."""

    uri = "genius://analytics"

    async def fetch(self, project_root: Path) -> dict[str, object]:
        try:
            from app.services.mcp.integrations import MCPIntegrations

            integrations = MCPIntegrations(project_root)
            return integrations.get_analytics_status()
        except Exception as e:
            return {"status": "error", "error": str(e)}


class VisionFetcher:
    """جلب معلومات خدمات الرؤية."""

    uri = "genius://vision"

    async def fetch(self, project_root: Path) -> dict[str, object]:
        try:
            from app.services.mcp.integrations import MCPIntegrations

            integrations = MCPIntegrations(project_root)
            return integrations.get_vision_status()
        except Exception as e:
            return {"status": "error", "error": str(e)}


class CollaborationFetcher:
    """جلب معلومات خدمات التعاون."""

    uri = "genius://collaboration"

    async def fetch(self, project_root: Path) -> dict[str, object]:
        try:
            from app.services.mcp.integrations import MCPIntegrations

            integrations = MCPIntegrations(project_root)
            return integrations.get_collaboration_status()
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ============== Registry للـ Fetchers ==============


def get_default_fetchers() -> list[IResourceFetcher]:
    """الحصول على قائمة الـ fetchers الافتراضية."""
    return [
        StructureFetcher(),
        MicroservicesFetcher(),
        DatabaseFetcher(),
        EnvironmentFetcher(),
        TechnologiesFetcher(),
        StatsFetcher(),
        # Genius Services
        LearningFetcher(),
        KnowledgeFetcher(),
        AnalyticsFetcher(),
        VisionFetcher(),
        CollaborationFetcher(),
    ]
