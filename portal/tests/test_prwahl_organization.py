"""Election permission invariants for the shared organization tree."""
from unittest.mock import Mock, patch
from fastapi import HTTPException
import pytest
from app.prwahl import scope

def test_org_leadership_without_election_mandate_has_no_access():
    db = Mock()
    election = Mock(org_id=17)
    db.get.return_value = election
    db.scalar.return_value = None
    user = Mock(id=3, active=True, is_admin=False)
    with patch("app.prwahl.active_path", return_value=[17]):
        with pytest.raises(HTTPException) as exc:
            scope(db, 4, user)
    assert exc.value.status_code == 404

def test_inactive_org_tree_blocks_even_existing_election_mandate():
    db = Mock()
    db.get.return_value = Mock(org_id=17)
    user = Mock(id=3, active=True)
    with patch("app.prwahl.active_path", return_value=[]):
        with pytest.raises(HTTPException) as exc:
            scope(db, 4, user)
    assert exc.value.status_code == 403

def test_inactive_account_blocks_election_access():
    db = Mock()
    db.get.return_value = Mock(org_id=17)
    with pytest.raises(HTTPException) as exc:
        scope(db, 4, Mock(id=3, active=False))
    assert exc.value.status_code == 403

def test_technical_coordinator_cannot_confirm_board_decisions():
    db = Mock()
    db.get.return_value = Mock(org_id=17)
    db.scalar.return_value = "coordinator"
    with patch("app.prwahl.active_path", return_value=[17]):
        with pytest.raises(HTTPException) as exc:
            scope(db, 4, Mock(id=3, active=True), "board")
    assert exc.value.status_code == 403
