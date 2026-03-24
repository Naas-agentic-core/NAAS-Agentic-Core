import math

from app.services.procedural_knowledge.domain import (
    AuditResult,
    AuditStatus,
    KnowledgeNode,
    NodeType,
    ProceduralGraph,
    Relation,
    RelationType,
)

# -------------------------------------------------------------------------
# 1. تعريف قواعد التدقيق الإجرائي (Procedural Rules)
# -------------------------------------------------------------------------


def verify_inventory_consistency(
    nodes: list[KnowledgeNode], relations: list[Relation]
) -> AuditResult:
    """
    قاعدة: التحقق من تطابق المخزون (الكرات) مع المجموع الكلي المصرح به.
    Metaphor: Fraud Detection - Inventory Audit.
    """
    urn_node = next((n for n in nodes if n.id == "urn_1"), None)
    if not urn_node:
        return AuditResult(
            rule_id="inventory_check",
            status=AuditStatus.FAIL,
            message="لم يتم العثور على الصندوق (Urn) في الرسم البياني.",
        )

    # استخراج البيانات
    red = urn_node.attributes.get("red_count", 0)
    green = urn_node.attributes.get("green_count", 0)
    declared_total = urn_node.attributes.get("total_count", 0)

    calculated_total = red + green

    if calculated_total == declared_total:
        return AuditResult(
            rule_id="inventory_check",
            status=AuditStatus.PASS,
            message=f"تطابق تام في المخزون: {red} أحمر + {green} أخضر = {declared_total} كلي.",
            evidence=[urn_node.id],
        )

    return AuditResult(
        rule_id="inventory_check",
        status=AuditStatus.FAIL,
        message=f"تزوير في الأعداد! المصرح به: {declared_total}، المحسوب فعلياً: {calculated_total}.",
        evidence=[urn_node.id],
    )


def _extract_probability_parameters(
    urn_node: KnowledgeNode, event_node: KnowledgeNode
) -> tuple[int, int, int, int, float]:
    """يستخرج معاملات الاحتمالات من العقد."""
    n = urn_node.attributes.get("total_count", 0)
    r = urn_node.attributes.get("red_count", 0)
    g = urn_node.attributes.get("green_count", 0)
    k = event_node.attributes.get("draw_count", 0)
    declared_prob = float(event_node.attributes.get("declared_probability", 0.0))
    return n, r, g, k, declared_prob


def _calculate_probability_metrics(n: int, r: int, g: int, k: int) -> tuple[int, int, int, float]:
    """يحسب احتمالات الحالات."""
    omega = math.comb(n, k)
    favorable_red = math.comb(r, k) if r >= k else 0
    favorable_green = math.comb(g, k) if g >= k else 0
    favorable_total = favorable_red + favorable_green
    calculated_prob = favorable_total / omega if omega > 0 else 0.0
    return omega, favorable_red, favorable_green, calculated_prob


def verify_probability_logic(nodes: list[KnowledgeNode], relations: list[Relation]) -> AuditResult:
    """
    قاعدة: التحقق من صحة الحساب المنطقي لاحتمال الحادثة A (سحب 3 كرات من نفس اللون).
    Metaphor: Fraud Detection - Transaction Logic Verification.
    """
    # 1. العثور على العقد
    urn_node = next((n for n in nodes if n.id == "urn_1"), None)
    event_node = next((n for n in nodes if n.id == "event_A"), None)

    if not urn_node or not event_node:
        return AuditResult(
            rule_id="logic_integrity_check",
            status=AuditStatus.WARNING,
            message="بيانات غير كافية للتحقق من المنطق.",
        )

    # 2. استخراج المعاملات
    n, r, g, k, declared_prob = _extract_probability_parameters(urn_node, event_node)

    # 3. الحساب الإجرائي (Procedural Calculation)
    omega, favorable_red, favorable_green, calculated_prob = _calculate_probability_metrics(
        n, r, g, k
    )

    # 4. المقارنة (مع تسامح بسيط للفاصلة العائمة)
    is_valid = abs(calculated_prob - declared_prob) < 1e-9

    evidence_msg = (
        f"المعطيات: n={n}, k={k}, R={r}, G={g}. "
        f"الحساب: (C({r},{k}) + C({g},{k})) / C({n},{k}) = ({favorable_red}+{favorable_green})/{omega} = {calculated_prob:.4f}"
    )

    if is_valid:
        return AuditResult(
            rule_id="logic_integrity_check",
            status=AuditStatus.PASS,
            message=f"المنطق سليم: الاحتمال المحسوب يطابق القيمة المصرح بها. {evidence_msg}",
            evidence=[event_node.id, urn_node.id],
        )

    return AuditResult(
        rule_id="logic_integrity_check",
        status=AuditStatus.FAIL,
        message=f"خطأ منطقي/احتيال! القيمة المصرح بها {declared_prob} لا تطابق الحساب {calculated_prob:.4f}.",
        evidence=[event_node.id],
    )


# -------------------------------------------------------------------------
# 2. بناء السيناريو (Data Factory)
# -------------------------------------------------------------------------


def load_bac_2024_scenario() -> tuple[ProceduralGraph, list]:
    """
    تحميل بيانات تمرين البكالوريا 2024 (شعبة علوم تجريبية، الموضوع 1، التمرين 1).
    """
    graph = ProceduralGraph()

    # --- العقد (Nodes) ---

    # 1. الصندوق (The Urn)
    urn = KnowledgeNode(
        id="urn_1",
        type=NodeType.ENTITY,
        label="كيس (Urn)",
        attributes={
            "red_count": 5,
            "green_count": 3,
            "total_count": 8,  # 5 + 3
            "description": "كيس يحتوي 8 كرات: 5 حمراء و 3 خضراء",
        },
    )
    graph.add_node(urn)

    # 2. التجربة (Experiment)
    exp = KnowledgeNode(
        id="experiment_draw",
        type=NodeType.EVENT,
        label="سحب عشوائي",
        attributes={
            "type": "simultaneous",  # في آن واحد
            "count": 3,
        },
    )
    graph.add_node(exp)

    # 3. الحادثة A (Event A)
    # الحساب: C(5,3)=10, C(3,3)=1. Omega = C(8,3)=56. Total=11/56.
    prob_val = (10 + 1) / 56  # ~0.1964

    event_a = KnowledgeNode(
        id="event_A",
        type=NodeType.CONCEPT,
        label="الحادثة A",
        attributes={
            "description": "الحصول على 3 كرات من نفس اللون",
            "draw_count": 3,
            "declared_probability": prob_val,
        },
    )
    graph.add_node(event_a)

    # --- العلاقات (Relations) ---

    graph.add_relation(
        Relation(
            source_id="urn_1",
            target_id="experiment_draw",
            type=RelationType.REQUIRES,
            metadata={"role": "subject"},
        )
    )

    graph.add_relation(
        Relation(
            source_id="experiment_draw",
            target_id="event_A",
            type=RelationType.DEFINES,
            metadata={"role": "outcome"},
        )
    )

    # --- القواعد (Rules) ---
    rules = [verify_inventory_consistency, verify_probability_logic]

    return graph, rules
