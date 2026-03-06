import uuid

from microservices.orchestrator_service.src.services.overmind.knowledge_graph_builder import (
    RELATION_AWARDED_TO,
    RELATION_BIDS_ON,
    RELATION_OWNED_BY,
    GraphBuildResult,
    ProcurementEntity,
    ProcurementRelation,
    build_procurement_graph,
    detect_triangular_fraud_signals,
)


def test_build_procurement_graph_creates_nodes_and_edges() -> None:
    entities = [
        ProcurementEntity(
            entity_type="vendor",
            entity_id="vendor-x",
            name="المورد X",
            metadata={"country": "AE"},
        ),
        ProcurementEntity(
            entity_type="tender",
            entity_id="tender-y",
            name="المناقصة Y",
            metadata={"value": 1200000},
        ),
        ProcurementEntity(
            entity_type="company",
            entity_id="company-z",
            name="الشركة Z",
            metadata={"registration": "Z-001"},
        ),
    ]
    relations = [
        ProcurementRelation(
            source_type="vendor",
            source_id="vendor-x",
            target_type="tender",
            target_id="tender-y",
            relation=RELATION_BIDS_ON,
            properties={"bid_amount": 1180000},
        ),
        ProcurementRelation(
            source_type="tender",
            source_id="tender-y",
            target_type="company",
            target_id="company-z",
            relation=RELATION_AWARDED_TO,
            properties={"award_date": "2025-01-11"},
        ),
        ProcurementRelation(
            source_type="vendor",
            source_id="vendor-x",
            target_type="company",
            target_id="company-z",
            relation=RELATION_OWNED_BY,
            properties={"ownership": 0.62},
        ),
    ]

    result = build_procurement_graph(entities=entities, relations=relations)

    assert isinstance(result, GraphBuildResult)
    assert len(result.nodes) == 3
    assert len(result.edges) == 3
    assert result.node_index[("vendor", "vendor-x")] in {node.node_id for node in result.nodes}


def test_detect_triangular_fraud_signals_flags_overlap() -> None:
    relations = [
        ProcurementRelation(
            source_type="vendor",
            source_id="vendor-x",
            target_type="tender",
            target_id="tender-y",
            relation=RELATION_BIDS_ON,
            properties={},
        ),
        ProcurementRelation(
            source_type="tender",
            source_id="tender-y",
            target_type="company",
            target_id="company-z",
            relation=RELATION_AWARDED_TO,
            properties={},
        ),
        ProcurementRelation(
            source_type="vendor",
            source_id="vendor-x",
            target_type="company",
            target_id="company-z",
            relation=RELATION_OWNED_BY,
            properties={},
        ),
    ]

    signals = detect_triangular_fraud_signals(relations)

    assert len(signals) == 1
    assert signals[0].vendor_id == "vendor-x"
    assert signals[0].company_id == "company-z"
    assert signals[0].tender_id == "tender-y"


def test_build_procurement_graph_uses_stable_ids() -> None:
    entities = [
        ProcurementEntity(
            entity_type="vendor",
            entity_id="vendor-x",
            name="المورد X",
            metadata={},
        )
    ]
    relations: list[ProcurementRelation] = []

    result = build_procurement_graph(
        entities=entities, relations=relations, namespace=uuid.NAMESPACE_DNS
    )
    second = build_procurement_graph(
        entities=entities, relations=relations, namespace=uuid.NAMESPACE_DNS
    )

    assert result.nodes[0].node_id == second.nodes[0].node_id
