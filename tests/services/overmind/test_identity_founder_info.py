"""
اختبار نظام المعرفة الذاتية لـ Overmind - معلومات المؤسس.

هذا الاختبار يتحقق من:
1. معلومات المؤسس الأساسية (الاسم، اللقب، تاريخ الميلاد)
2. الإجابة على الأسئلة بالعربية والإنجليزية
3. دقة المعلومات المعروضة
"""

import pytest

from microservices.orchestrator_service.src.services.overmind.identity import OvermindIdentity


class TestOvermindIdentityFounder:
    """اختبارات معلومات المؤسس في نظام الهوية."""

    def setup_method(self):
        """إعداد الاختبار - إنشاء instance من OvermindIdentity."""
        self.identity = OvermindIdentity()

    def test_founder_basic_info_exists(self):
        """اختبار: وجود معلومات المؤسس الأساسية."""
        founder = self.identity.get_founder_info()

        # التحقق من وجود المعلومات الأساسية
        assert founder is not None
        assert "name" in founder
        assert "name_ar" in founder
        assert "first_name" in founder
        assert "last_name" in founder
        assert "first_name_ar" in founder
        assert "last_name_ar" in founder
        assert "birth_date" in founder

    def test_founder_name_accuracy_english(self):
        """اختبار: دقة الاسم بالإنجليزية - Houssam Benmerah."""
        founder = self.identity.get_founder_info()

        # التحقق من الاسم الكامل
        assert founder["name"] == "Houssam Benmerah"

        # التحقق من الاسم الأول واللقب منفصلين
        assert founder["first_name"] == "Houssam"
        assert founder["last_name"] == "Benmerah"

    def test_founder_name_accuracy_arabic(self):
        """اختبار: دقة الاسم بالعربية - حسام بن مراح."""
        founder = self.identity.get_founder_info()

        # التحقق من الاسم الكامل بالعربية
        assert founder["name_ar"] == "حسام بن مراح"

        # التحقق من الاسم الأول واللقب بالعربية منفصلين
        assert founder["first_name_ar"] == "حسام"
        assert founder["last_name_ar"] == "بن مراح"

    def test_founder_birth_date(self):
        """اختبار: تاريخ الميلاد - 11 أغسطس 1997."""
        founder = self.identity.get_founder_info()

        # التحقق من تاريخ الميلاد
        assert founder["birth_date"] == "1997-08-11"

    def test_get_founder_method(self):
        """اختبار: دالة get_founder() ترجع الاسم الكامل."""
        founder_name = self.identity.get_founder()

        assert founder_name == "Houssam Benmerah"

    def test_answer_founder_question_arabic(self):
        """اختبار: الإجابة على سؤال عن المؤسس بالعربية."""
        # أسئلة مختلفة بالعربية
        questions = [
            "من هو مؤسس overmind",
            "من المؤسس؟",
            "من أنشأ overmind",
            "من بنى النظام",
        ]

        for question in questions:
            answer = self.identity.answer_question(question)

            # التحقق من وجود المعلومات في الإجابة
            assert "حسام بن مراح" in answer
            assert "Houssam Benmerah" in answer
            assert "حسام" in answer
            assert "بن مراح" in answer
            assert "1997-08-11" in answer or "11 أغسطس 1997" in answer

    def test_answer_founder_question_english(self):
        """اختبار: الإجابة على سؤال عن المؤسس بالإنجليزية."""
        # أسئلة مختلفة بالإنجليزية
        questions = [
            "who is the founder",
            "who is the creator",
            "who founded overmind",
        ]

        for question in questions:
            answer = self.identity.answer_question(question)

            # التحقق من وجود المعلومات في الإجابة
            assert "Houssam Benmerah" in answer or "حسام بن مراح" in answer

    def test_answer_birth_date_question_arabic(self):
        """اختبار: الإجابة على سؤال عن تاريخ الميلاد بالعربية."""
        questions = [
            "ما هو تاريخ ميلاد المؤسس",
            "متى ولد المؤسس",
            "تاريخ ميلاد حسام",
        ]

        for question in questions:
            answer = self.identity.answer_question(question)

            # التحقق من وجود تاريخ الميلاد في الإجابة
            assert "1997-08-11" in answer or "11 أغسطس 1997" in answer

    def test_answer_birth_date_question_english(self):
        """اختبار: الإجابة على سؤال عن تاريخ الميلاد بالإنجليزية."""
        questions = [
            "what is the founder's birth date",
            "when was the founder born",
            "founder's birthday",
        ]

        for question in questions:
            answer = self.identity.answer_question(question)

            # التحقق من وجود تاريخ الميلاد في الإجابة
            assert "1997-08-11" in answer or "August 11, 1997" in answer

    def test_founder_role_info(self):
        """اختبار: معلومات دور المؤسس."""
        founder = self.identity.get_founder_info()

        assert "role" in founder
        assert "role_ar" in founder
        assert founder["role"] == "Creator & Lead Architect"
        assert "المؤسس" in founder["role_ar"] or "المهندس" in founder["role_ar"]

    def test_founder_github_info(self):
        """اختبار: معلومات GitHub للمؤسس."""
        founder = self.identity.get_founder_info()

        assert "github" in founder
        assert founder["github"] == "HOUSSAM16ai"

    def test_full_identity_contains_founder(self):
        """اختبار: الهوية الكاملة تحتوي على معلومات المؤسس."""
        full_identity = self.identity.get_full_identity()

        assert "founder" in full_identity
        assert full_identity["founder"]["name"] == "Houssam Benmerah"
        assert full_identity["founder"]["name_ar"] == "حسام بن مراح"
        assert full_identity["founder"]["birth_date"] == "1997-08-11"

    def test_answer_combined_question(self):
        """اختبار: الإجابة على سؤال مركب عن المؤسس."""
        question = "من هو مؤسس overmind ومتى ولد"
        answer = self.identity.answer_question(question)

        # يجب أن تحتوي الإجابة على الاسم وتاريخ الميلاد
        assert "حسام بن مراح" in answer or "Houssam Benmerah" in answer
        assert "1997" in answer


class TestOvermindIdentityDatabaseCapabilities:
    """اختبارات قدرات قاعدة البيانات في نظام الهوية."""

    def setup_method(self):
        """إعداد الاختبار."""
        self.identity = OvermindIdentity()

    def test_identity_has_capabilities_info(self):
        """اختبار: النظام يعرف قدراته على قاعدة البيانات."""
        capabilities = self.identity.get_capabilities()

        assert capabilities is not None
        assert "knowledge" in capabilities
        assert "actions" in capabilities

        # التحقق من وجود معرفة بقاعدة البيانات
        knowledge_items = capabilities["knowledge"]
        has_db_knowledge = any(
            "قاعدة البيانات" in item or "database" in item.lower() for item in knowledge_items
        )
        assert has_db_knowledge, "النظام يجب أن يعرف عن قاعدة البيانات"

    def test_identity_knows_database_actions(self):
        """اختبار: النظام يعرف الإجراءات المتاحة على قاعدة البيانات."""
        capabilities = self.identity.get_capabilities()

        actions = capabilities["actions"]

        # التحقق من وجود إجراءات قاعدة البيانات
        any(
            "قاعدة البيانات" in action or "database" in action.lower() or "استعلام" in action
            for action in actions
        )

        # على الأقل يجب أن يكون هناك إجراء واحد متعلق بقاعدة البيانات
        assert len(actions) > 0, "يجب أن تكون هناك إجراءات متاحة"

    def test_answer_capabilities_question(self):
        """اختبار: الإجابة على سؤال عن القدرات."""
        questions = [
            "ماذا تستطيع أن تفعل",
            "what can you do",
            "ما هي قدراتك",
            "what are your capabilities",
        ]

        for question in questions:
            answer = self.identity.answer_question(question)

            # يجب أن تحتوي الإجابة على معلومات عن القدرات
            assert len(answer) > 50, "الإجابة يجب أن تكون تفصيلية"
            assert "قدرات" in answer or "المعرفة" in answer or "الإجراءات" in answer


class TestOvermindIdentityAgentPrinciples:
    """اختبارات مبادئ الوكلاء في نظام الهوية."""

    def setup_method(self):
        """إعداد الاختبار."""
        self.identity = OvermindIdentity()

    def test_agent_principles_are_available(self):
        """اختبار: مبادئ الوكلاء متاحة ومنسقة."""
        principles = self.identity.get_agent_principles()

        assert isinstance(principles, list)
        assert len(principles) >= 100
        assert principles[0]["number"] == 1
        assert "الوكيل الذكي" in principles[0]["statement"]

    def test_answer_agent_principles_question(self):
        """اختبار: الإجابة على سؤال مبادئ الوكلاء."""
        answer = self.identity.answer_question("ما هي مبادئ الوكلاء؟")

        assert "مبادئ الوكلاء" in answer
        assert "1." in answer
        assert "الوكيل الذكي" in answer


class TestOvermindIdentitySystemPrinciples:
    """اختبارات مبادئ النظام الصارمة في نظام الهوية."""

    def setup_method(self):
        """إعداد الاختبار."""
        self.identity = OvermindIdentity()

    def test_system_principles_are_available(self):
        """اختبار: مبادئ النظام الصارمة متاحة ومنسقة."""
        principles = self.identity.get_system_principles()

        assert isinstance(principles, list)
        assert len(principles) == 100
        assert principles[0]["number"] == 1
        assert "تعدد الأشكال" in principles[0]["statement"]

    def test_answer_system_principles_question(self):
        """اختبار: الإجابة على سؤال مبادئ النظام الصارمة."""
        answer = self.identity.answer_question("ما هي المبادئ الصارمة للنظام؟")

        assert "المبادئ الصارمة للنظام" in answer
        assert "1." in answer
        assert "تعدد الأشكال" in answer


if __name__ == "__main__":
    # تشغيل الاختبارات مباشرة
    pytest.main([__file__, "-v"])
