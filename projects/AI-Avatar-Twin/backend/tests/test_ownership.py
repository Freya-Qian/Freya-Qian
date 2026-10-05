"""Profile 归属双重校验测试：_get_profile_for_topic 沿链路逐层校验 user_id。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import AvatarProfile, Project, Source, SourceItem, Topic
from app.api.routes import _get_profile_for_topic


def _make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return Session()


def test_profile_ownership_mismatch_returns_none():
    db = _make_session()
    prof = AvatarProfile(id="p1", user_id="u2", project_id="prj1", name="x")
    proj = Project(id="prj1", user_id="u1", name="p", default_avatar_profile_id="p1")
    src = Source(id="s1", user_id="u1", project_id="prj1", source_type="url", url="https://x")
    item = SourceItem(id="i1", user_id="u1", source_id="s1", original_url="https://x")
    topic = Topic(id="t1", user_id="u1", source_item_id="i1")
    db.add_all([prof, proj, src, item, topic])
    db.commit()
    # profile 属于 u2，不应返回给 u1
    assert _get_profile_for_topic(db, topic, "u1") is None


def test_profile_ownership_match_returns_profile():
    db = _make_session()
    prof = AvatarProfile(id="p1", user_id="u1", project_id="prj1", name="x")
    proj = Project(id="prj1", user_id="u1", name="p", default_avatar_profile_id="p1")
    src = Source(id="s1", user_id="u1", project_id="prj1", source_type="url", url="https://x")
    item = SourceItem(id="i1", user_id="u1", source_id="s1", original_url="https://x")
    topic = Topic(id="t1", user_id="u1", source_item_id="i1")
    db.add_all([prof, proj, src, item, topic])
    db.commit()
    result = _get_profile_for_topic(db, topic, "u1")
    assert result is not None and result.id == "p1"
