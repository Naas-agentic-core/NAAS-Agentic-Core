"""
اختبارات شاملة لمكونات MCP Resources.
====================================

يغطي:
- MCPResource: إنشاء وتحويل للقاموس
- MCPResourceProvider: تهيئة وجلب الموارد والتخزين المؤقت
- Resource Fetchers: استراتيجيات جلب الموارد
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMCPResource:
    """اختبارات MCPResource."""

    def test_create_resource_with_defaults(self):
        """إنشاء مورد بالقيم الافتراضية."""
        from app.services.mcp.resources import MCPResource

        resource = MCPResource(
            uri="test://resource",
            name="اختبار",
            description="وصف الاختبار",
        )

        assert resource.uri == "test://resource"
        assert resource.name == "اختبار"
        assert resource.description == "وصف الاختبار"
        assert resource.mime_type == "application/json"

    def test_create_resource_with_custom_mime_type(self):
        """إنشاء مورد بنوع محتوى مخصص."""
        from app.services.mcp.resources import MCPResource

        resource = MCPResource(
            uri="test://text",
            name="نص",
            description="مورد نصي",
            mime_type="text/plain",
        )

        assert resource.mime_type == "text/plain"

    def test_to_dict(self):
        """تحويل المورد لقاموس."""
        from app.services.mcp.resources import MCPResource

        resource = MCPResource(
            uri="project://test",
            name="اختبار",
            description="وصف",
        )

        result = resource.to_dict()

        assert result == {
            "uri": "project://test",
            "name": "اختبار",
            "description": "وصف",
            "mimeType": "application/json",
        }


class TestMCPResourceProvider:
    """اختبارات MCPResourceProvider."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """إنشاء بنية مشروع وهمية."""
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "main.py").write_text("# Main app")
        return tmp_path

    @pytest.fixture
    def mock_fetcher(self):
        """إنشاء fetcher وهمي."""
        fetcher = MagicMock()
        fetcher.uri = "project://mock"
        fetcher.fetch = AsyncMock(return_value={"mock": "data"})
        return fetcher

    async def test_initialize_creates_resources(self, project_root, mock_fetcher):
        """التهيئة تُنشئ الموارد."""
        from app.services.mcp.resources import MCPResourceProvider

        provider = MCPResourceProvider(project_root, fetchers=[mock_fetcher])
        await provider.initialize()

        assert len(provider.resources) == 11
        assert "project://structure" in provider.resources
        assert "project://database" in provider.resources
        assert "project://environment" in provider.resources
        assert "project://microservices" in provider.resources
        assert "project://technologies" in provider.resources
        assert "project://stats" in provider.resources

    async def test_get_resource_not_found(self, project_root, mock_fetcher):
        """جلب مورد غير موجود."""
        from app.services.mcp.resources import MCPResourceProvider

        provider = MCPResourceProvider(project_root, fetchers=[mock_fetcher])
        await provider.initialize()

        result = await provider.get_resource("project://nonexistent")

        assert "error" in result
        assert "available_resources" in result

    async def test_get_resource_uses_fetcher(self, project_root):
        """جلب المورد يستخدم الـ fetcher المناسب."""
        from app.services.mcp.resources import MCPResourceProvider

        mock_fetcher = MagicMock()
        mock_fetcher.uri = "project://structure"
        mock_fetcher.fetch = AsyncMock(return_value={"files": 10})

        provider = MCPResourceProvider(project_root, fetchers=[mock_fetcher])
        await provider.initialize()

        result = await provider.get_resource("project://structure")

        assert result == {"files": 10}
        mock_fetcher.fetch.assert_called_once_with(project_root)

    async def test_get_resource_caching(self, project_root):
        """التخزين المؤقت يعمل."""
        from app.services.mcp.resources import MCPResourceProvider

        mock_fetcher = MagicMock()
        mock_fetcher.uri = "project://structure"
        mock_fetcher.fetch = AsyncMock(return_value={"cached": True})

        provider = MCPResourceProvider(project_root, fetchers=[mock_fetcher])
        await provider.initialize()

        # الاستدعاء الأول
        await provider.get_resource("project://structure")
        # الاستدعاء الثاني
        await provider.get_resource("project://structure")

        # يجب أن يُستدعى مرة واحدة فقط
        assert mock_fetcher.fetch.call_count == 1

    async def test_clear_cache(self, project_root):
        """مسح التخزين المؤقت."""
        from app.services.mcp.resources import MCPResourceProvider

        mock_fetcher = MagicMock()
        mock_fetcher.uri = "project://structure"
        mock_fetcher.fetch = AsyncMock(return_value={"data": 1})

        provider = MCPResourceProvider(project_root, fetchers=[mock_fetcher])
        await provider.initialize()

        await provider.get_resource("project://structure")
        assert len(provider._cache) == 1

        provider.clear_cache()

        assert len(provider._cache) == 0

    async def test_list_resources(self, project_root, mock_fetcher):
        """قائمة الموارد المتاحة."""
        from app.services.mcp.resources import MCPResourceProvider

        provider = MCPResourceProvider(project_root, fetchers=[mock_fetcher])
        await provider.initialize()

        resources = provider.list_resources()

        assert len(resources) == 11
        assert all("uri" in r for r in resources)
        assert all("name" in r for r in resources)

    async def test_register_fetcher(self, project_root):
        """تسجيل fetcher جديد."""
        from app.services.mcp.resources import MCPResourceProvider

        provider = MCPResourceProvider(project_root, fetchers=[])

        new_fetcher = MagicMock()
        new_fetcher.uri = "project://custom"
        new_fetcher.fetch = AsyncMock(return_value={"custom": True})

        provider.register_fetcher(new_fetcher)

        assert "project://custom" in provider._fetchers


class TestResourceFetchers:
    """اختبارات Resource Fetchers."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """إنشاء بنية مشروع للاختبارات."""
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "main.py").write_text("def main(): pass")

        services_dir = app_dir / "services"
        services_dir.mkdir()
        (services_dir / "test.py").write_text("class TestService: pass")

        return tmp_path

    async def test_structure_fetcher(self, project_root):
        """اختبار StructureFetcher."""
        from app.services.mcp.protocols import StructureFetcher

        fetcher = StructureFetcher()

        assert fetcher.uri == "project://structure"

        with patch("microservices.orchestrator_service.src.services.overmind.knowledge_structure.build_project_structure") as mock:
            mock.return_value = {"python_files": 5}
            result = await fetcher.fetch(project_root)
            assert result == {"python_files": 5}

    async def test_microservices_fetcher(self, project_root):
        """اختبار MicroservicesFetcher."""
        from app.services.mcp.protocols import MicroservicesFetcher

        fetcher = MicroservicesFetcher()

        assert fetcher.uri == "project://microservices"

        with patch("microservices.orchestrator_service.src.services.overmind.knowledge_structure.build_microservices_summary") as mock:
            mock.return_value = {"total_services": 3}
            result = await fetcher.fetch(project_root)
            assert result == {"total_services": 3}

    async def test_technologies_fetcher(self, project_root):
        """اختبار TechnologiesFetcher."""
        from app.services.mcp.protocols import TechnologiesFetcher

        fetcher = TechnologiesFetcher()

        assert fetcher.uri == "project://technologies"

        result = await fetcher.fetch(project_root)

        assert "ai_frameworks" in result
        assert "backend" in result
        assert any(f["name"] == "LangGraph" for f in result["ai_frameworks"])

    async def test_database_fetcher_with_mock_knowledge(self, project_root):
        """اختبار DatabaseFetcher مع knowledge وهمي."""
        from app.services.mcp.protocols import DatabaseFetcher

        mock_knowledge = MagicMock()
        mock_knowledge.get_database_info = AsyncMock(return_value={"tables": ["users", "sessions"]})

        fetcher = DatabaseFetcher(knowledge=mock_knowledge)
        result = await fetcher.fetch(project_root)

        assert result == {"tables": ["users", "sessions"]}

    async def test_database_fetcher_handles_error(self, project_root):
        """اختبار DatabaseFetcher يتعامل مع الأخطاء."""
        from app.services.mcp.protocols import DatabaseFetcher

        mock_knowledge = MagicMock()
        mock_knowledge.get_database_info = AsyncMock(side_effect=Exception("Connection failed"))

        fetcher = DatabaseFetcher(knowledge=mock_knowledge)
        result = await fetcher.fetch(project_root)

        assert "error" in result
        assert "Connection failed" in result["error"]

    async def test_get_default_fetchers(self):
        """اختبار الحصول على fetchers الافتراضية."""
        from app.services.mcp.protocols import get_default_fetchers

        fetchers = get_default_fetchers()

        assert len(fetchers) == 11

        uris = [f.uri for f in fetchers]
        assert "project://structure" in uris
        assert "project://microservices" in uris
        assert "project://database" in uris
        assert "project://environment" in uris
        assert "project://technologies" in uris
        assert "project://stats" in uris
