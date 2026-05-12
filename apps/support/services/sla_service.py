# apps/support/services/sla_service.py
"""
SLA (Service Level Agreement) Tracking Service — Fashionistar Support Domain.

Architecture
────────────
  - Compute SLA deadlines based on ticket priority at creation time.
  - Evaluate breach status on demand (no scheduled celery dependency required).
  - Expose aggregated SLA metrics for the admin operations dashboard.
  - All computations are purely time-based (no external I/O); safe to call in
    both sync DRF views and async Ninja endpoints.

SLA Matrix (CBN / internal Fashionistar SLA commitment)
──────────────────────────────────────────────────────
  Priority   First Response   Resolution
  ─────────  ──────────────   ──────────
  urgent     30 minutes       4 hours
  high       2 hours          24 hours
  medium     8 hours          72 hours
  low        24 hours         168 hours (7 days)

Breach Categories
─────────────────
  - RESPONSE_BREACH: No staff reply within first_response_deadline.
  - RESOLUTION_BREACH: Ticket not RESOLVED/CLOSED by resolution_deadline.
  - AT_RISK: Within 20% of the SLA deadline (pre-breach warning).
  - ON_TRACK: No SLA concerns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SLA Configuration
# ─────────────────────────────────────────────────────────────────────────────

# (first_response_minutes, resolution_minutes)
_SLA_MATRIX: dict[str, tuple[int, int]] = {
    "urgent": (30,   240),    # 30 min / 4 hr
    "high":   (120,  1440),   # 2 hr  / 24 hr
    "medium": (480,  4320),   # 8 hr  / 72 hr
    "low":    (1440, 10080),  # 24 hr / 7 days
}

# Percentage of SLA window used that triggers AT_RISK
_AT_RISK_THRESHOLD = 0.80  # 80% elapsed = AT_RISK

# Breach status codes
BREACH_ON_TRACK        = "on_track"
BREACH_AT_RISK         = "at_risk"
BREACH_RESPONSE_BREACH = "response_breach"
BREACH_RESOLUTION      = "resolution_breach"


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class SLAConfig:
    """SLA deadline configuration for a given priority."""
    priority: str
    first_response_minutes: int
    resolution_minutes: int

    @property
    def first_response_delta(self) -> timedelta:
        return timedelta(minutes=self.first_response_minutes)

    @property
    def resolution_delta(self) -> timedelta:
        return timedelta(minutes=self.resolution_minutes)


@dataclass(slots=True)
class SLAStatus:
    """
    Computed SLA health status for a single ticket.

    Attributes:
        ticket_id:              UUID string of the ticket.
        priority:               Ticket priority at evaluation time.
        created_at:             Ticket creation timestamp.
        first_response_deadline: When the first staff reply is due.
        resolution_deadline:    When the ticket must be resolved.
        first_response_at:      Timestamp of first staff reply (or None).
        breach_status:          One of the BREACH_* constants.
        response_breach:        True if no staff reply before deadline.
        resolution_breach:      True if ticket not resolved before deadline.
        minutes_to_response:    Minutes remaining until response deadline (negative = overdue).
        minutes_to_resolution:  Minutes remaining until resolution deadline (negative = overdue).
        elapsed_pct:            % of resolution window elapsed (for AT_RISK computation).
    """
    ticket_id:              str
    priority:               str
    created_at:             object  # datetime
    first_response_deadline: object  # datetime
    resolution_deadline:    object  # datetime
    first_response_at:      Optional[object] = field(default=None)  # datetime | None
    breach_status:          str = field(default=BREACH_ON_TRACK)
    response_breach:        bool = field(default=False)
    resolution_breach:      bool = field(default=False)
    minutes_to_response:    float = field(default=0.0)
    minutes_to_resolution:  float = field(default=0.0)
    elapsed_pct:            float = field(default=0.0)


# ─────────────────────────────────────────────────────────────────────────────
# SLAService
# ─────────────────────────────────────────────────────────────────────────────

class SLAService:
    """
    Stateless SLA computation service.

    All methods are pure functions of their inputs — no DB I/O performed here.
    Callers are responsible for fetching tickets and passing them in.

    Usage (DRF view)::

        from apps.support.services.sla_service import SLAService

        ticket = SupportTicket.objects.get(pk=pk)
        sla = SLAService.evaluate_ticket(ticket)
        if sla.response_breach:
            alert_on_call_staff(sla)

    Usage (Ninja async endpoint)::

        tickets = await SupportTicket.objects.filter(...).aall()
        statuses = [SLAService.evaluate_ticket(t) for t in tickets]
    """

    # ── Config lookup ─────────────────────────────────────────────────────────

    @classmethod
    def get_config(cls, priority: str) -> SLAConfig:
        """
        Return SLA configuration for the given priority.
        Falls back to 'medium' defaults for unknown priorities.
        """
        first_resp, resolution = _SLA_MATRIX.get(
            priority,
            _SLA_MATRIX["medium"],
        )
        return SLAConfig(
            priority=priority,
            first_response_minutes=first_resp,
            resolution_minutes=resolution,
        )

    # ── Single ticket evaluation ──────────────────────────────────────────────

    @classmethod
    def evaluate_ticket(cls, ticket) -> SLAStatus:
        """
        Compute SLA health for a single SupportTicket.

        Args:
            ticket: SupportTicket model instance.

        Returns:
            SLAStatus dataclass with all computed fields.
        """
        from apps.support.models import TicketStatus, TicketMessage

        config = cls.get_config(ticket.priority)
        now = timezone.now()
        created = ticket.created_at

        # Compute deadlines
        first_response_deadline = created + config.first_response_delta
        resolution_deadline     = created + config.resolution_delta

        # Find first staff reply timestamp
        first_response_at: Optional[object] = None
        try:
            first_staff_msg = (
                TicketMessage.objects.filter(ticket=ticket, is_staff_reply=True)
                .order_by("created_at")
                .first()
            )
            if first_staff_msg:
                first_response_at = first_staff_msg.created_at
        except Exception:
            pass  # Fail silently — SLA computation must never crash

        # Compute remaining time
        minutes_to_response   = (first_response_deadline - now).total_seconds() / 60
        minutes_to_resolution = (resolution_deadline - now).total_seconds() / 60

        # Elapsed % of resolution window
        total_window = config.resolution_delta.total_seconds()
        elapsed = (now - created).total_seconds()
        elapsed_pct = min(elapsed / total_window, 1.0) if total_window > 0 else 1.0

        # Breach evaluation
        is_terminal = ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED)

        response_breach = (
            first_response_at is None
            and not is_terminal
            and now > first_response_deadline
        )

        resolution_breach = (
            not is_terminal
            and now > resolution_deadline
        )

        # Determine overall breach status
        if resolution_breach:
            breach_status = BREACH_RESOLUTION
        elif response_breach:
            breach_status = BREACH_RESPONSE_BREACH
        elif elapsed_pct >= _AT_RISK_THRESHOLD and not is_terminal:
            breach_status = BREACH_AT_RISK
        else:
            breach_status = BREACH_ON_TRACK

        return SLAStatus(
            ticket_id=str(ticket.id),
            priority=ticket.priority,
            created_at=created,
            first_response_deadline=first_response_deadline,
            resolution_deadline=resolution_deadline,
            first_response_at=first_response_at,
            breach_status=breach_status,
            response_breach=response_breach,
            resolution_breach=resolution_breach,
            minutes_to_response=round(minutes_to_response, 1),
            minutes_to_resolution=round(minutes_to_resolution, 1),
            elapsed_pct=round(elapsed_pct * 100, 1),
        )

    # ── Batch evaluation ──────────────────────────────────────────────────────

    @classmethod
    def evaluate_batch(cls, tickets) -> list[SLAStatus]:
        """
        Evaluate SLA status for a collection of tickets.

        Args:
            tickets: Iterable of SupportTicket instances.

        Returns:
            List of SLAStatus objects (same order as input).
        """
        return [cls.evaluate_ticket(t) for t in tickets]

    # ── Metrics aggregation ───────────────────────────────────────────────────

    @classmethod
    def compute_metrics(cls, tickets) -> dict:
        """
        Aggregate SLA health metrics across a set of tickets.

        Intended for the admin operations dashboard (superadmin-only).

        Returns:
            dict with keys:
              total          — total ticket count
              on_track       — tickets meeting all SLA targets
              at_risk        — tickets approaching SLA breach
              response_breach — tickets missing first-response SLA
              resolution_breach — tickets overdue for resolution
              breach_rate_pct — (response + resolution) / total * 100
        """
        statuses = cls.evaluate_batch(tickets)
        total = len(statuses)

        counts = {
            BREACH_ON_TRACK:        0,
            BREACH_AT_RISK:         0,
            BREACH_RESPONSE_BREACH: 0,
            BREACH_RESOLUTION:      0,
        }
        for s in statuses:
            counts[s.breach_status] = counts.get(s.breach_status, 0) + 1

        breached = counts[BREACH_RESPONSE_BREACH] + counts[BREACH_RESOLUTION]
        breach_rate = round(breached / total * 100, 1) if total else 0.0

        return {
            "total":             total,
            "on_track":          counts[BREACH_ON_TRACK],
            "at_risk":           counts[BREACH_AT_RISK],
            "response_breach":   counts[BREACH_RESPONSE_BREACH],
            "resolution_breach": counts[BREACH_RESOLUTION],
            "breach_rate_pct":   breach_rate,
        }

    # ── Overdue ticket detection ───────────────────────────────────────────────

    @classmethod
    def get_overdue_ticket_ids(cls, tickets) -> list[str]:
        """
        Return ticket IDs that are in BREACH_RESPONSE_BREACH or
        BREACH_RESOLUTION — for automated escalation workflows.

        Args:
            tickets: Iterable of SupportTicket instances.

        Returns:
            List of UUID strings for tickets requiring immediate action.
        """
        statuses = cls.evaluate_batch(tickets)
        return [
            s.ticket_id
            for s in statuses
            if s.breach_status in (BREACH_RESPONSE_BREACH, BREACH_RESOLUTION)
        ]

    # ── Helper: deadline serialization ───────────────────────────────────────

    @staticmethod
    def serialize_sla(sla: SLAStatus) -> dict:
        """
        Convert an SLAStatus to a JSON-serializable dict for API responses.

        Returns:
            dict suitable for ``SLAStatusSchema`` or direct JSON serialization.
        """
        return {
            "ticket_id":              sla.ticket_id,
            "priority":               sla.priority,
            "breach_status":          sla.breach_status,
            "response_breach":        sla.response_breach,
            "resolution_breach":      sla.resolution_breach,
            "minutes_to_response":    sla.minutes_to_response,
            "minutes_to_resolution":  sla.minutes_to_resolution,
            "elapsed_pct":            sla.elapsed_pct,
            "first_response_deadline": (
                sla.first_response_deadline.isoformat()
                if sla.first_response_deadline else None
            ),
            "resolution_deadline": (
                sla.resolution_deadline.isoformat()
                if sla.resolution_deadline else None
            ),
            "first_response_at": (
                sla.first_response_at.isoformat()
                if sla.first_response_at else None
            ),
        }
