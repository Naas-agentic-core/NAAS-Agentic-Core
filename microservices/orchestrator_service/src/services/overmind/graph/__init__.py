"""حزمة الرسم البياني لوحدة Overmind مع استيراد كسول لتقليل التبعيات وقت التحميل."""


def create_unified_graph(*args, **kwargs):
    """ينشئ الرسم البياني الموحّد عند الطلب مع تحميل متأخر للوحدة الثقيلة."""
    from .main import create_unified_graph as _create_unified_graph

    return _create_unified_graph(*args, **kwargs)


__all__ = ["create_unified_graph"]
