from pathlib import Path


def test_supplier_repository_uses_business_partner_and_supplier_role() -> None:
    source = Path("app/modules/suppliers/infrastructure/repository.py").read_text()
    assert 'SUPPLIER_ROLE = "SUPPLIER"' in source
    assert "BusinessPartnerModel" in source
    assert "PartnerRoleModel" in source
    assert "SupplierModel" not in source


def test_multi_role_create_attaches_role_to_existing_partner() -> None:
    source = Path("app/modules/suppliers/infrastructure/repository.py").read_text()
    assert "if existing:" in source
    assert "partner_id=existing.id" in source
    assert "supplier_user_assignments" not in source


def test_supplier_scope_uses_role_specific_assignments() -> None:
    source = Path("app/modules/suppliers/infrastructure/repository.py").read_text()
    assert "SupplierUserAssignmentModel" in source
    assert "SupplierGroupAssignmentModel" in source
    assert "CustomerUserAssignmentModel" not in source
