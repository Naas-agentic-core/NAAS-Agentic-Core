"""
وحدة التوافق (Compatibility Module).
-----------------------------------
توفر طبقة تجريد لمكتبة llama-index، مما يسمح بتشغيل الخدمة
حتى في حالة عدم توفر المكتبة (استخدام Fallback/Mock).
"""

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field


def _load_llama_index() -> tuple[object | None, object | None]:
    """يحاول تحميل وحدات LlamaIndex اللازمة لسير العمل عند توفرها."""

    try:
        if importlib.util.find_spec("llama_index") is None:
            return None, None
    except ValueError:
        # Happens if llama_index namespace is present but module is invalid/missing spec
        return None, None

    schema_spec = importlib.util.find_spec("llama_index.core.schema")
    workflow_spec = importlib.util.find_spec("llama_index.core.workflow")
    if schema_spec is None or workflow_spec is None:
        return None, None

    schema_module = importlib.import_module("llama_index.core.schema")
    workflow_module = importlib.import_module("llama_index.core.workflow")
    return schema_module, workflow_module


_schema_module, _workflow_module = _load_llama_index()

if _schema_module is None or _workflow_module is None:

    @dataclass
    class TextNode:
        """تمثيل مبسط لعقدة نصية."""

        text: str = ""
        metadata: dict[str, str] = field(default_factory=dict)

    @dataclass
    class NodeWithScore:
        """تمثيل مبسط لعقدة معرفة مع نص وبيانات وصفية."""

        node: TextNode
        score: float = 0.0

        @property
        def text(self) -> str:
            return self.node.text

        @property
        def metadata(self) -> dict[str, str]:
            return self.node.metadata

    class Event:
        """حدث بسيط يدعم تخزين البيانات وقراءتها."""

        def __init__(self, **payload: object) -> None:
            self._payload = payload

        def get(self, key: str, default: object | None = None) -> object | None:
            return self._payload.get(key, default)

    class StartEvent(Event):
        """حدث البداية لسير العمل المبسط."""

    class StopEvent(Event):
        """حدث النهاية لسير العمل المبسط."""

    class Context:
        """سياق فارغ لسير العمل المبسط."""

    class Workflow:
        """قالب مبسط لسير العمل عند غياب LlamaIndex."""

        def __init__(self, timeout: int = 300, verbose: bool = True) -> None:
            self.timeout = timeout
            self.verbose = verbose

        async def run(self, **kwargs: object) -> object:
            """دالة تشغيل وهمية للاختبارات."""
            return None

    def step(func: Callable[..., object]) -> Callable[..., object]:
        """ديكوريتر بديل لا يغير سلوك الدالة."""

        return func

else:
    NodeWithScore = _schema_module.NodeWithScore
    TextNode = _schema_module.TextNode
    Context = _workflow_module.Context
    Event = _workflow_module.Event
    StartEvent = _workflow_module.StartEvent
    StopEvent = _workflow_module.StopEvent
    Workflow = _workflow_module.Workflow
    step = _workflow_module.step
