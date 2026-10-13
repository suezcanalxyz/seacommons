"""Futures invitation security and review tests (isolated in-memory SQLite)."""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from core.db.models import Base, FuturesInvitationDB, FuturesInvitationReviewDB
from core.api.routes.futures_invitations import InvitationInput, identity
from core.config import config


def test_email_validation():
    assert InvitationInput(first_name='A', last_name='B', email='a@example.org').email == 'a@example.org'
    with pytest.raises(ValueError):
        InvitationInput(first_name='A', last_name='B', email='not-an-email')


def test_no_development_identity(monkeypatch):
    monkeypatch.setattr(config, 'AUTH_ENABLED', False)
    with pytest.raises(HTTPException) as error:
        identity(None)
    assert error.value.status_code == 503


def test_invitation_schema_is_persistent():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine, tables=[FuturesInvitationDB.__table__, FuturesInvitationReviewDB.__table__])
    with Session(engine) as session:
        session.add(FuturesInvitationDB(id='test', first_name='A', last_name='B', email='a@example.org', proposed_by='actor', status='pending'))
        session.commit()
        assert session.get(FuturesInvitationDB, 'test').status == 'pending'
