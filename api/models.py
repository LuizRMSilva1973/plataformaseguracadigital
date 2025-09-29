from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    plan = Column(String, nullable=False, default="starter")
    ingest_token = Column(String, nullable=False, unique=True)
    alert_email = Column(String, nullable=True)
    integrations_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    users = relationship("User", back_populates="tenant")
    subscription = relationship("Subscription", back_populates="tenant", uselist=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    tenant = relationship("Tenant", back_populates="users")
    password_hash = Column(String, nullable=True)


class Agent(Base):
    __tablename__ = "agents"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    os = Column(String, nullable=True)
    version = Column(String, nullable=True)
    last_seen_at = Column(DateTime(timezone=True))
    status = Column(String, default="active")


class IngestBatch(Base):
    __tablename__ = "ingest_batches"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    batch_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint('tenant_id', 'agent_id', 'batch_id', name='uq_batch'),)


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    host = Column(String, nullable=True)
    app = Column(String, nullable=True)
    event_type = Column(String, nullable=True)
    src_ip = Column(String, nullable=True)
    dst_ip = Column(String, nullable=True)
    username = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    raw_json = Column(JSON, nullable=True)


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    kind = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    first_seen = Column(DateTime(timezone=True), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=False)
    count = Column(Integer, nullable=False, default=1)
    context_json = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="open")


class IPReputation(Base):
    __tablename__ = "ip_reputation_cache"
    ip = Column(String, primary_key=True)
    asn = Column(String, nullable=True)
    country = Column(String, nullable=True)
    score = Column(Integer, nullable=True)
    source = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    url_pdf = Column(String, nullable=True)
    score = Column(Integer, nullable=True)
    summary_json = Column(JSON, nullable=True)


class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    host = Column(String, nullable=False)
    os = Column(String, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    agent_id = Column(String, nullable=True)
    __table_args__ = (UniqueConstraint('tenant_id', 'host', name='uq_asset_tenant_host'),)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    kind = Column(String, nullable=False)  # incident, digest, system
    severity = Column(String, nullable=True)
    channel = Column(String, nullable=True)  # email, whatsapp, webhook
    payload_json = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending|sent|failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())



class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    price = Column(Integer, nullable=False)  # In cents
    stripe_price_id = Column(String, nullable=False, unique=True)
    features = Column(JSON, nullable=True)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, unique=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    provider = Column(String, nullable=False, default="stripe")
    stripe_customer_id = Column(String, nullable=False, unique=True)
    stripe_subscription_id = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="subscription")
    plan = relationship("Plan")



class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    ts = Column(DateTime(timezone=True), server_default=func.now())


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    key = Column(String, nullable=False)
    title = Column(String, nullable=False)
    context_json = Column(JSON, nullable=True)
    done = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint('tenant_id', 'key', name='uq_checklist_key'),)


class BlockedIP(Base):
    __tablename__ = "blocked_ips"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    ip = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint('tenant_id', 'ip', 'provider', name='uq_blocked_ip'),)
