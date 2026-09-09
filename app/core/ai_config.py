"""
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                          ║
║   ██████╗ ██████╗  ██████╗ ███╗   ██╗██╗███████╗ ██████╗ ██████╗  ██████╗ ███████╗      ║
║  ██╔════╝██╔═══██╗██╔════╝ ████╗  ██║██║██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝      ║
║  ██║     ██║   ██║██║  ███╗██╔██╗ ██║██║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗        ║
║  ██║     ██║   ██║██║   ██║██║╚██╗██║██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝        ║
║  ╚██████╗╚██████╔╝╚██████╔╝██║ ╚████║██║██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗      ║
║   ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝      ║
║                                                                                          ║
║              🧠 AI MODELS CONFIGURATION CENTER v2.1 - SUPERHUMAN EDITION                ║
║              ════════════════════════════════════════════════════════════                ║
║                                                                                          ║
║   ╔════════════════════════════════════════════════════════════════════════════════╗    ║
║   ║  📍 THIS IS THE ONLY FILE YOU NEED TO EDIT TO CHANGE AI MODELS                ║    ║
║   ║  📍 هذا هو الملف الوحيد الذي تحتاج تعديله لتغيير نماذج الذكاء الاصطناعي         ║    ║
║   ╚════════════════════════════════════════════════════════════════════════════════╝    ║
║                                                                                          ║
║   🔧 HOW TO CHANGE MODELS | كيفية تغيير النماذج:                                        ║
║      1. Scroll down to "ACTIVE CONFIGURATION" section                                   ║
║      2. Change the model values directly                                                ║
║      3. Save the file and restart the application                                       ║
║                                                                                          ║
║      1. انزل إلى قسم "ACTIVE CONFIGURATION"                                             ║
║      2. غيّر قيم النماذج مباشرة                                                          ║
║      3. احفظ الملف وأعد تشغيل التطبيق                                                    ║
║                                                                                          ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _resolve_primary_model(default_model: str) -> str:
    """يحلّ نموذج التشغيل الأساسي من البيئة مع قيمة افتراضية آمنة."""
    override_model = os.getenv("OPENROUTER_PRIMARY_MODEL", "").strip()
    if override_model:
        return override_model
    return default_model


def get_openrouter_site_url() -> str:
    """يقرأ OPENROUTER_SITE_URL من البيئة — يُستخدم كـ HTTP-Referer في طلبات OpenRouter."""
    return os.getenv("OPENROUTER_SITE_URL", "https://cogniforge.local").strip()


class AvailableModels:
    """
    📚 All Available AI Models | جميع النماذج المتاحة

    Copy the model ID (the string value) to use in the configuration below.
    انسخ معرف النموذج (القيمة النصية) لاستخدامه في التكوين أدناه.
    """

    GPT_4O = "openai/gpt-4o"
    GPT_4O_MINI = "nvidia/nemotron-3-nano-30b-a3b:free"
    GPT_4_TURBO = "openai/gpt-4-turbo"
    GPT_4 = "openai/gpt-4"
    GPT_35_TURBO = "openai/gpt-3.5-turbo"
    CLAUDE_37_SONNET_THINKING = "anthropic/claude-3.7-sonnet:thinking"
    CLAUDE_35_SONNET = "anthropic/claude-3.5-sonnet"
    CLAUDE_OPUS_4_5 = "anthropic/claude-opus-4.5"
    CLAUDE_3_OPUS = "anthropic/claude-3-opus"
    CLAUDE_3_HAIKU = "anthropic/claude-3-haiku"
    GEMINI_PRO = "google/gemini-pro"
    GEMINI_PRO_15 = "google/gemini-pro-1.5"
    LLAMA_3_70B = "meta-llama/llama-3-70b-instruct"
    LLAMA_3_8B = "meta-llama/llama-3-8b-instruct"
    # ISS-070 (2026-05-15): نماذج مُتحقَّق منها حياً — gemini-2.0-flash-exp و llama-3.2-11b-vision غير متاحة
    LLAMA_3_2_11B_VISION_FREE = "openai/gpt-oss-20b:free"
    GEMINI_2_FLASH_EXP_FREE = "google/gemma-4-26b-a4b-it:free"
    PHI_3_MINI_FREE = "z-ai/glm-4.5-air:free"
    KAT_CODER_PRO_FREE = "openai/gpt-oss-120b:free"
    QWEN_QWEN3_CODER_FREE = "qwen/qwen3-coder:free"
    # ISS-069 (2026-05-15): نماذج عاملة مُحدَّثة بعد بنشمارك حي
    NEMOTRON_3_SUPER_120B_FREE = "nvidia/nemotron-3-super-120b-a12b:free"
    GPT_OSS_120B_FREE = "openai/gpt-oss-120b:free"
    GPT_OSS_20B_FREE = "openai/gpt-oss-20b:free"
    TRINITY_LARGE_THINKING_FREE = "arcee-ai/trinity-large-thinking:free"
    NEMOTRON_3_NANO = "nvidia/nemotron-3-nano-30b-a3b:free"


class ActiveModels:
    """
    ⚙️ ACTIVE AI MODELS CONFIGURATION | تكوين النماذج النشط

    ╔═══════════════════════════════════════════════════════════════════════════════════╗
    ║                                                                                   ║
    ║   🔧 TO CHANGE A MODEL:                                                          ║
    ║      1. Find the model you want to change below                                  ║
    ║      2. Replace the value with one from AvailableModels above                    ║
    ║      3. Save and restart                                                         ║
    ║                                                                                   ║
    ║   🔧 لتغيير نموذج:                                                               ║
    ║      1. ابحث عن النموذج الذي تريد تغييره أدناه                                   ║
    ║      2. استبدل القيمة بواحدة من AvailableModels أعلاه                            ║
    ║      3. احفظ وأعد التشغيل                                                        ║
    ║                                                                                   ║
    ╚═══════════════════════════════════════════════════════════════════════════════════╝
    """

    # ISS-STREAM-002: inclusionai/ring-2.6-1t:free كنموذج أساسي موحَّد عبر النظام
    # nemotron-3-super-120b-a12b:free كان يُعيد chunk واحد فقط → لا typing effect
    # ISS-STREAM-003: inclusionai/ring-2.6-1t:free — النموذج الوحيد المتاح حالياً
    # الذي يدعم streaming حقيقي (كلمة وراء كلمة) عبر OpenRouter (2026-05-13).
    # ISS-055: nemotron-3-nano-30b-a3b — TTFT=2.06s مع context 9670 حرف، عربية صحيحة
    # inclusionai/ring-2.6-1t:free — fallback سريع للاسترجاع
    # ISS-069 (2026-05-15): بنشمارك حي كشف أن nemotron-3-nano-omni-30b-a3b-reasoning:free
    # يضع الإجابة في delta.reasoning لا delta.content → content=None دائماً مع system prompt
    # → إجابات فارغة/كارثية للطلاب. الحل: العودة لـ nemotron-3-nano-30b-a3b:free
    # الذي أثبت: جودة 4/4، TTFT=3.1s، عربية صحيحة، LaTeX سليم، content مضمون.
    # ISS-079 (D-067 — 2026-05-17): تجريب حي حي حقيقي على 5 نماذج مع
    # system prompt الإنتاجي الكامل (1690 chars) كشف:
    # ❌ nvidia/nemotron-nano-30b-a3b → content=None (راح إلى reasoning بالإنجليزية)
    # ❌ nvidia/nemotron-super-120b → English reasoning (لا عربي)
    # ❌ z-ai/glm-4.5-air → content=None، reasoning كله
    # ✅ openai/gpt-oss-20b → 2102 chunks، 4762 chars، finish=stop، عربي + LaTeX نقي
    # ✅ openai/gpt-oss-120b → 2480 chunks، 5502 chars، أفضل جودة
    # القرار: التحويل إلى gpt-oss-20b كنموذج أساسي (يحل ISS-079 كارثة pepepe).
    # ISS-082 (D-088 — 2026-05-27): تجريب حي على بيئة الإنتاج كشف أن
    # gpt-oss-20b:free أصبح rate-limited بشكل دائم على OpenRouter
    # ("Provider returned error 429"). كل WS chat يفشل صامتاً بـ chunks=0.
    # gpt-oss-120b:free من نفس العائلة (OpenAI OSS) ومحقَّق حي يعمل ✅.
    # نفس quality contract لـ gpt-oss-20b (D-067) لكن rate limit pool مختلف.
    # gpt-oss-20b يبقى في الـ fallback chain — إن تعافى من 429 سيُستخدم تلقائياً.
    # ISS-130 (D-167 — 2026-07-14): gpt-oss-120b:free أُزيل نهائياً من OpenRouter
    # (404) ⇒ إعادة ترقية gpt-oss-20b (الـ PRIMARY المُتحقَّق تاريخياً — D-067،
    # وتعافى من 429 — مُتحقَّق حياً 10.2s عربي+LaTeX finish=stop).
    PRIMARY = _resolve_primary_model("openai/gpt-oss-20b:free")
    LOW_COST = PRIMARY
    GATEWAY_PRIMARY = PRIMARY
    # ISS-107 (2026-06-02): بنشمارك حي بالمفتاح الحقيقي + الـ system prompt الإنتاجي
    # كشف أن السلسلة القديمة تنحدر إلى نماذج كارثية عند ضغط gpt-oss:
    #   ❌ nvidia/nemotron-3-super-120b → "We need to respond in Arabic..." (إنجليزي في content)
    #   ❌ z-ai/glm-4.5-air → content فارغ (reasoning-only)
    #   ❌ arcee-ai/trinity-large-thinking → HTTP 404 (غير موجود)
    # ✅ verified Arabic content (full prompt): gpt-oss-120b، gpt-oss-20b.
    # nemotron-nano: عربي سريع مع prompt قصير، لكن reasoning-only مع prompt طويل (D-067)
    #   — آمن الآن بفضل guard "content_chunks==0 → advance" + Arabic stream guard (ISS-107).
    # gemma-4/qwen3-next/kimi: نماذج instruct كبيرة (429 وقت البنشمارك)، محميّة بالحُرّاس.
    # ISS-108 (D-097 — 2026-06-03): بنشمارك حي بالمفتاح الحقيقي كشف أن
    # gpt-oss-120b + gpt-oss-20b كلاهما 503 (Service Unavailable) بشكل **دائم**
    # (4 جولات متتالية). عند هذا الانقطاع كانت السلسلة تصل أولاً إلى
    # nemotron-3-nano (محظور كـ PRIMARY — reasoning-only مع prompt طويل، D-067)
    # قبل gemma. التحقق الحي: gemma-4-26b = GOOD (عربي 65% + LaTeX + لا تسرّب).
    # الحل: تقديم gemma على nemotron في سلسلة الاحتياط — أسلم نموذج صحيّ يُبلَغ
    # أولاً عند سقوط gpt-oss. PRIMARY يبقى gpt-oss-120b (يتعافى آلياً عند عودته).
    # ISS-130 (D-167 — 2026-07-14): OpenRouter أزال النسخة المجانية من
    # gpt-oss-120b نهائياً (404 «This model is unavailable for free») — منتج
    # لا انقطاع. بنشمارك حي قانوني (system prompt عربي + مشتق ln(x)):
    #   ✅ gpt-oss-20b:free      → 10.2s، عربي + LaTeX، finish=stop (الأسرع الصحيح)
    #   ✅ gemma-4-26b-a4b-it    → 20.1s، عربي + LaTeX، finish=stop
    #   ✅ gemma-4-31b-it        → 12.3s، عربي + LaTeX، finish=stop (جديد)
    #   ❌ gpt-oss-120b:free     → 404 (أُزيل من الطبقة المجانية)
    #   ❌ qwen3-next / kimi-k2.6 / qwen3-coder / llama-3.3-70b → ميتة/Provider error
    #   ⚠️ nemotron-3-nano       → هلوسة يابانية (يؤكّد حظر D-067 كـ PRIMARY)
    # القرار: إعادة ترقية gpt-oss-20b إلى PRIMARY (هو الـ PRIMARY المُتحقَّق تاريخياً
    # D-067)؛ gemma-4 بإصداريه بعده؛ gpt-oss-120b يبقى في ذيل السلسلة كفتحة
    # تعافٍ آلي إن أعاد OpenRouter نسخته المجانية (الحُرّاس يتجاوزون 404 فوراً).
    GATEWAY_FALLBACK_1 = "google/gemma-4-26b-a4b-it:free"  # ✅ GOOD حياً (2026-07-14) — عربي+LaTeX
    GATEWAY_FALLBACK_2 = "google/gemma-4-31b-it:free"  # ✅ GOOD حياً (2026-07-14) — عربي+LaTeX
    GATEWAY_FALLBACK_3 = "nvidia/nemotron-3-nano-30b-a3b:free"  # سريع؛ محميّ بـ content==0 guard
    GATEWAY_FALLBACK_4 = "openai/gpt-oss-120b:free"  # ميت 404 (2026-07-14) — فتحة تعافٍ آلي
    GATEWAY_FALLBACK_5 = "nvidia/nemotron-nano-9b-v2:free"  # ملاذ أخير؛ محميّ بالحُرّاس (D-177: FIRST_TOKEN_TIMEOUT يحدّ تعليقه 62s؛ nemotron-3-super-120b يبقى محظوراً ISS-107 — تسرّب إنجليزي)
    TIER_NANO = PRIMARY
    TIER_FAST = PRIMARY
    TIER_SMART = PRIMARY
    TIER_GENIUS = PRIMARY


@dataclass(frozen=True)
class AIConfig:
    """
    AI Configuration singleton - reads from ActiveModels class.
    """

    primary_model: str = ActiveModels.PRIMARY
    low_cost_model: str = ActiveModels.LOW_COST
    gateway_primary: str = ActiveModels.GATEWAY_PRIMARY
    gateway_fallback_1: str = ActiveModels.GATEWAY_FALLBACK_1
    gateway_fallback_2: str = ActiveModels.GATEWAY_FALLBACK_2
    gateway_fallback_3: str = ActiveModels.GATEWAY_FALLBACK_3
    gateway_fallback_4: str = ActiveModels.GATEWAY_FALLBACK_4
    gateway_fallback_5: str = ActiveModels.GATEWAY_FALLBACK_5
    tier_nano: str = ActiveModels.TIER_NANO
    tier_fast: str = ActiveModels.TIER_FAST
    tier_smart: str = ActiveModels.TIER_SMART
    tier_genius: str = ActiveModels.TIER_GENIUS

    @property
    def openrouter_api_key(self) -> str | None:
        """
        🔑 Access API Key securely from the Central Nervous System (Settings).
        يسترجع مفتاح API بأمان من النظام المركزي (Settings).
        """
        return get_settings().OPENROUTER_API_KEY

    def get_fallback_models(self) -> list[str]:
        """Get list of fallback models.

        D-177: the five pinned constants stay first (safety order, ISS-079). Any
        models named in ``OPENROUTER_EXTRA_MODELS`` (comma-separated) are appended
        as an *additional* tail — this is the zero-code path to plug a paid /
        higher-tier OpenRouter model (which accumulates its own rate limits) so
        the chain keeps answering even when the whole free tier is 429. The
        env-extras are runtime-only and never alter the parity-gated literals.
        """
        chain = [
            self.gateway_fallback_1,
            self.gateway_fallback_2,
            self.gateway_fallback_3,
            self.gateway_fallback_4,
            self.gateway_fallback_5,
        ]
        extra = os.getenv("OPENROUTER_EXTRA_MODELS", "").strip()
        if extra:
            for model in (m.strip() for m in extra.split(",")):
                if model and model not in chain and model != self.primary_model:
                    chain.append(model)
        return chain

    def to_dict(self) -> dict:
        """Export configuration as dictionary."""
        return {
            "primary_model": self.primary_model,
            "low_cost_model": self.low_cost_model,
            "gateway": {
                "primary": self.gateway_primary,
                "fallback_1": self.gateway_fallback_1,
                "fallback_2": self.gateway_fallback_2,
                "fallback_3": self.gateway_fallback_3,
                "fallback_4": self.gateway_fallback_4,
                "fallback_5": self.gateway_fallback_5,
            },
            "tiers": {
                "nano": self.tier_nano,
                "fast": self.tier_fast,
                "smart": self.tier_smart,
                "genius": self.tier_genius,
            },
        }

    def log_config(self) -> None:
        """Log current configuration."""
        logger.info(
            """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    🧠 CURRENT AI MODELS CONFIGURATION                        ║
╠══════════════════════════════════════════════════════════════════════════════╣"""
        )
        logger.info("║  🎯 Primary Model:     %s ║", f"{self.primary_model:<50}")
        logger.info("║  💰 Low Cost Model:    %s ║", f"{self.low_cost_model:<50}")
        logger.info(
            "╠══════════════════════════════════════════════════════════════════════════════╣"
        )
        logger.info("║  🌟 Gateway Primary:   %s ║", f"{self.gateway_primary:<50}")
        logger.info("║  🔄 Fallback 1:        %s ║", f"{self.gateway_fallback_1:<50}")
        logger.info("║  🔄 Fallback 2:        %s ║", f"{self.gateway_fallback_2:<50}")
        logger.info("║  🔄 Fallback 3:        %s ║", f"{self.gateway_fallback_3:<50}")
        logger.info("║  🔄 Fallback 4:        %s ║", f"{self.gateway_fallback_4:<50}")
        logger.info("║  🔄 Fallback 5:        %s ║", f"{self.gateway_fallback_5:<50}")
        logger.info(
            "╠══════════════════════════════════════════════════════════════════════════════╣"
        )
        logger.info("║  ⚡ Tier NANO:         %s ║", f"{self.tier_nano:<50}")
        logger.info("║  🚀 Tier FAST:         %s ║", f"{self.tier_fast:<50}")
        logger.info("║  🧠 Tier SMART:        %s ║", f"{self.tier_smart:<50}")
        logger.info("║  🎓 Tier GENIUS:       %s ║", f"{self.tier_genius:<50}")
        logger.info(
            "╚══════════════════════════════════════════════════════════════════════════════╝"
        )


@lru_cache(maxsize=1)
def get_ai_config() -> AIConfig:
    """Get the AI configuration singleton."""
    return AIConfig()


ai_config = get_ai_config()
__all__ = ["AIConfig", "ActiveModels", "AvailableModels", "ai_config", "get_ai_config"]

if __name__ == "__main__":
    logger.info("📋 Available Models for Reference:")
    logger.info("─" * 60)
    logger.info("  OpenAI GPT-4o:           %s", AvailableModels.GPT_4O)
    logger.info("  OpenAI GPT-4o-mini:      %s", AvailableModels.GPT_4O_MINI)
    logger.info("  Claude 3.7 Sonnet:       %s", AvailableModels.CLAUDE_37_SONNET_THINKING)
    logger.info("  Claude 3.5 Sonnet:       %s", AvailableModels.CLAUDE_35_SONNET)
    logger.info("  Claude 3 Opus:           %s", AvailableModels.CLAUDE_3_OPUS)
    logger.info("─" * 60)
    config = get_ai_config()
    config.log_config()
