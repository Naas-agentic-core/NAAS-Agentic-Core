from app.core.domain.voucher import Entitlement


def test_entitlement_has_composite_index():
    indexes = list(Entitlement.__table__.indexes)

    # Check that our specific composite index exists
    composite_index = None
    for idx in indexes:
        if idx.name == "ix_entitlements_user_id_expires_at_id":
            composite_index = idx
            break

    assert composite_index is not None, "Composite index not found"

    # Verify the columns in the index are exactly as expected
    columns = [col.name for col in composite_index.columns]
    assert columns == ["user_id", "expires_at", "id"]

    # Ensure the redundant user_id index was removed from the model
    user_id_index = None
    for idx in indexes:
        # A single column index on user_id
        if len(idx.columns) == 1 and next(iter(idx.columns)).name == "user_id":
            user_id_index = idx
            break

    assert user_id_index is None, "Standalone user_id index should be removed from the model"
