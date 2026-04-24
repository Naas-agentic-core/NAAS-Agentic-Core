"""
Intent Detector Service.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class ChatIntent(StrEnum):
    """Supported Chat Intents."""

    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    CODE_SEARCH = "CODE_SEARCH"
    PROJECT_INDEX = "PROJECT_INDEX"
    DEEP_ANALYSIS = "DEEP_ANALYSIS"
    MISSION_COMPLEX = "MISSION_COMPLEX"
    ANALYTICS_REPORT = "ANALYTICS_REPORT"
    LEARNING_SUMMARY = "LEARNING_SUMMARY"
    CURRICULUM_PLAN = "CURRICULUM_PLAN"
    CONTENT_RETRIEVAL = "CONTENT_RETRIEVAL"
    ADMIN_QUERY = "ADMIN_QUERY"
    HELP = "HELP"
    DEFAULT = "DEFAULT"


@dataclass(frozen=True, slots=True)
class IntentPattern:
    """Intent Pattern Specification."""

    pattern: str
    intent: ChatIntent
    extractor: Callable[[re.Match[str]], dict[str, str]]


@dataclass(frozen=True, slots=True)
class IntentResult:
    """Intent Detection Result."""

    intent: ChatIntent
    confidence: float
    params: dict[str, str]


class IntentDetector:
    """
    Detects user intent using regex patterns.
    """

    def __init__(self) -> None:
        self._patterns = self._build_patterns()

    def _build_patterns(self) -> list[IntentPattern]:
        """Builds intent patterns."""
        return [
            IntentPattern(pattern=pattern, intent=intent, extractor=extractor)
            for pattern, intent, extractor in self._pattern_specs()
        ]

    def _pattern_specs(
        self,
    ) -> list[tuple[str, ChatIntent, Callable[[re.Match[str]], dict[str, str]]]]:
        """Defines pattern specifications."""
        admin_queries = [
            r"(user|users|مستخدم|مستخدمين|count users|list users|profile|stats|أعضاء|إحصائيات)",
            r"(database|schema|tables|db map|database map|قاعدة بيانات|قاعدة البيانات|جداول|مخطط|بنية البيانات|خريطة قاعدة البيانات|العلاقات)",
            r"(route|endpoint|api path|مسار api|نقطة نهاية|services|microservices|خدمات|مصغرة)",
            r"(structure|project info|هيكل المشروع|معلومات المشروع|بنية النظام)",
            r"(python|بايثون|\.py)",
            r"(files|ملفات|ملف|file\s*count|عدد\s*ملفات)",
            r"(count|احسب|حساب|كمية|عدّ)\s*(python|files|ملفات|بايثون|المشروع)",
            r"(كم)\s*(عدد)?\s*(ملف|ملفات|بايثون|python|\.py)",
            r"(count_python|count_files|python_files)",
        ]
        analytics_keywords = (
            r"(مستواي|أدائي|نقاط ضعفي|نقاط الضعف|تقييم|level|performance|weakness|report"
            r"|تشخيص\s*(نقاط|الضعف|أداء|الأداء|مستواي)|تقييم\s*مستواي|اختبرني|"
            r"تشخيص\s*مستواي)"
        )
        return [
            *[(pattern, ChatIntent.ADMIN_QUERY, self._empty_params) for pattern in admin_queries],
            (r"(حلل|analyze|explain|اشرح)\s+(.+)", ChatIntent.DEEP_ANALYSIS, self._empty_params),
            (
                r"((أ|ا)ريد|بدي|i want|need|show|أعطني|هات|give me)?\s*(.*)(20[1-2][0-9]|bac|بكالوريا|subject|topic|lesson|درس|موضوع|تمارين|تمرين|exam|exercise|exercises|احتمالات|دوال|متتاليات|probability|functions|sequences)(.+)?",
                ChatIntent.CONTENT_RETRIEVAL,
                self._extract_query_optional,
            ),
            (
                r"(نص|text)\s+(التمرين|تمرين|exercise|exercises)\b(.+)?",
                ChatIntent.CONTENT_RETRIEVAL,
                self._extract_query_optional,
            ),
            (
                r"(read|open|show|cat|اقرا|اقرأ|اعرض|عرض)\s+(file|ملف)\s+(.+)",
                ChatIntent.FILE_READ,
                self._extract_path,
            ),
            (
                r"(ابحث|search|find|where|أين|اين)\s+(عن|for)?\s*(.+)",
                ChatIntent.CODE_SEARCH,
                self._extract_query,
            ),
            (r"(فهرس|index)\s+(المشروع|project)", ChatIntent.PROJECT_INDEX, self._empty_params),
            (analytics_keywords, ChatIntent.ANALYTICS_REPORT, self._empty_params),
            (
                r"(ملخص|تلخيص|خلاصة|لخص|summarize|summary)"
                r".*(ما تعلمت|ما تعلمته|تعلمي|محادثاتي|دردشاتي|سجلي|what i learned|what i've learned|my learning|my chats|my history)",
                ChatIntent.LEARNING_SUMMARY,
                self._empty_params,
            ),
            (
                r"(واجب|مسار|تعلم|homework|learning path|challenge|خطة|خريطة|منهج|plan|roadmap|study plan|ابدأ|start studying)",
                ChatIntent.CURRICULUM_PLAN,
                self._empty_params,
            ),
            (r"(مساعدة|help)", ChatIntent.HELP, self._empty_params),
        ]

    async def detect(self, question: str) -> IntentResult:
        """Detects intent from simplified question."""
        question_lower = question.lower().strip()

        for pattern in self._patterns:
            match = re.search(pattern.pattern, question_lower, re.IGNORECASE)
            if match:
                params = pattern.extractor(match)
                confidence = self._calculate_confidence(match)
                return IntentResult(
                    intent=pattern.intent,
                    confidence=confidence,
                    params=params,
                )

        if self._is_complex_mission(question):
            return IntentResult(intent=ChatIntent.MISSION_COMPLEX, confidence=0.7, params={})

        return IntentResult(intent=ChatIntent.DEFAULT, confidence=1.0, params={})

    def _extract_path(self, match: re.Match[str]) -> dict[str, str]:
        return {"path": match.group(3).strip()}

    def _extract_query(self, match: re.Match[str]) -> dict[str, str]:
        return {"query": match.group(3).strip()}

    def _extract_query_optional(self, match: re.Match[str]) -> dict[str, str]:
        return {"query": match.group(0).strip()}

    @staticmethod
    def _empty_params(_: re.Match[str]) -> dict[str, str]:
        return {}

    def _calculate_confidence(self, match: re.Match[str]) -> float:
        return 0.9 if match else 0.5

    def _is_complex_mission(self, question: str) -> bool:
        if self._matches_analytics_intent(question):
            return False
        indicators = [
            "قم ب",
            "نفذ",
            "أنشئ",
            "طور",
            "implement",
            "create",
            "build",
            "develop",
        ]
        return any(indicator in question.lower() for indicator in indicators)

    def _matches_analytics_intent(self, question: str) -> bool:
        analytics_pattern = (
            r"(مستواي|أدائي|نقاط ضعفي|نقاط الضعف|تقييم|level|performance|weakness|report"
            r"|تشخيص|اختبرني|assessment|quiz|test)"
        )
        return bool(re.search(analytics_pattern, question, re.IGNORECASE))
