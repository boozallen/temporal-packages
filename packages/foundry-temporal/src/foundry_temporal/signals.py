# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Signal Pattern Helpers for Human-in-the-Loop Workflows

Standard signal patterns based on foundry-temporal architecture specifications.
"""

import hmac
from typing import Any

from temporalio import workflow

from ._limits import bound_signal_comment


def _approval_args(args: tuple[Any, ...]) -> tuple[str, str] | None:
    """Return ``(approver_id, content_digest)`` from raw signal args, or ``None``.

    Signal handlers take ``*args`` so Temporal never raises on a wrong argument
    count. Exactly two arguments are required: a non-empty ``approver_id`` string
    and an ASCII ``content_digest`` string (such as a SHA-256 hex digest). An
    ASCII check also rejects lone surrogates, which cannot be encoded.
    """
    if len(args) != 2:
        return None
    approver_id, content_digest = args
    if not isinstance(approver_id, str) or not approver_id:
        return None
    if not isinstance(content_digest, str) or not content_digest.isascii():
        return None
    return approver_id, content_digest


def _feedback_args(args: tuple[Any, ...]) -> tuple[str, Any] | None:
    """Return ``(approver_id, comments)`` from raw signal args, or ``None``.

    Exactly two arguments are required, the first a non-empty ``approver_id``
    string. A legacy comments-only call has one argument and is rejected, so
    its text is never read as an approver. ``comments`` is normalized later by
    ``bound_signal_comment``.
    """
    if len(args) != 2:
        return None
    approver_id, comments = args
    if not isinstance(approver_id, str) or not approver_id:
        return None
    return approver_id, comments


def _accept_approval(
    instance,
    args: tuple[Any, ...],
    *,
    open_attr: str,
    digest_attr: str,
    approved_attr: str,
    approved_by_attr: str,
    feedback_received_attr: str | None = None,
    feedback_comments_attr: str | None = None,
) -> None:
    """Shared approver/digest/open-lane binding for approval signals.

    Requires valid ``(approver_id, content_digest)`` args (see
    ``_approval_args``) and a ``content_digest`` matching the digest recorded
    under ``digest_attr``, while ``open_attr`` is true; otherwise a silent
    no-op (signal handlers must not raise). On acceptance, records the
    approver, clears the paired feedback state when given, and closes the lane.
    """
    parsed = _approval_args(args)
    if parsed is None or not getattr(instance, open_attr, False):
        return
    approver_id, content_digest = parsed
    expected = getattr(instance, digest_attr, None)
    if not isinstance(expected, str) or not expected.isascii():
        return
    if not hmac.compare_digest(content_digest.encode("ascii"), expected.encode("ascii")):
        return
    setattr(instance, approved_attr, True)
    setattr(instance, approved_by_attr, approver_id)
    if feedback_received_attr is not None:
        setattr(instance, feedback_received_attr, False)
    if feedback_comments_attr is not None:
        setattr(instance, feedback_comments_attr, "")
    setattr(instance, open_attr, False)


def _accept_feedback(
    instance,
    args: tuple[Any, ...],
    *,
    received_attr: str,
    comments_attr: str,
    approved_attr: str | None = None,
) -> None:
    """Shared approver-required binding for feedback signals.

    Requires valid ``(approver_id, comments)`` args (see ``_feedback_args``);
    otherwise a silent no-op. On acceptance, records the bounded comment
    (STIG V-222612) and clears the paired approval flag when given.
    """
    parsed = _feedback_args(args)
    if parsed is None:
        return
    _, comments = parsed
    setattr(instance, received_attr, True)
    setattr(instance, comments_attr, bound_signal_comment(comments))
    if approved_attr is not None:
        setattr(instance, approved_attr, False)


def _approval_attribute_name(signal_name: str) -> str:
    """Return the predictable boolean attribute name a signal_name's approval sets.

    ``"approve"`` maps to ``"approved"`` (matching ``HILSignalsMixin``'s own
    general approval attribute); any other name maps to ``"<name>_approved"``
    (e.g. ``"deployment"`` maps to ``"deployment_approved"``). This replaces
    the previous ad hoc past-tense guessing, which produced non-words for
    names that are not bare verbs (e.g. ``"deployment"`` produced
    ``"deploymented"``).
    """
    if signal_name == "approve":
        return "approved"
    return f"{signal_name}_approved"


class HILSignalsMixin:
    """
    Mixin class providing standard Human-in-the-Loop signal patterns.

    Every approval signal requires a non-empty ``approver_id``
    and a ``content_digest`` matching the digest of the content currently open for
    review; it is a silent no-op otherwise (signals must not raise). Call
    ``open_plan_review``/``open_document_review``/``open_review`` with the digest
    of the content being presented before waiting on the corresponding approve
    signal. ``cancel_workflow`` and the feedback signals require ``approver_id``
    but are not phase- or digest-gated.

    Usage:
        class MyWorkflow(HILSignalsMixin):
            def __init__(self):
                super().__init__()
                # Your workflow initialization

            async def run(self):
                digest = hashlib.sha256(plan_text.encode()).hexdigest()
                self.open_plan_review(digest)
                await workflow.wait_condition(self.is_plan_decision_received)
    """

    def __init__(self):
        super().__init__()
        # General approval state
        self.approved: bool = False
        self.approved_by: str | None = None
        self._review_open: bool = False
        self._expected_digest: str | None = None

        # Plan review state
        self.plan_approved: bool = False
        self.plan_approved_by: str | None = None
        self.plan_feedback_received: bool = False
        self.plan_feedback_comments: str = ""
        self._plan_review_open: bool = False
        self._expected_plan_digest: str | None = None

        # Document review state
        self.document_approved: bool = False
        self.document_approved_by: str | None = None
        self.document_feedback_received: bool = False
        self.document_feedback_comments: str = ""
        self._document_review_open: bool = False
        self._expected_document_digest: str | None = None

        # General feedback state
        self.cancelled: bool = False
        self.cancelled_by: str | None = None

    # Review-open helpers (called by the workflow, not signals themselves)
    def open_plan_review(self, content_digest: str) -> None:
        """Open the plan lane for review, resetting its prior decision state."""
        self.plan_approved = False
        self.plan_approved_by = None
        self.plan_feedback_received = False
        self.plan_feedback_comments = ""
        self._expected_plan_digest = content_digest
        self._plan_review_open = True

    def open_document_review(self, content_digest: str) -> None:
        """Open the document lane for review, resetting its prior decision state."""
        self.document_approved = False
        self.document_approved_by = None
        self.document_feedback_received = False
        self.document_feedback_comments = ""
        self._expected_document_digest = content_digest
        self._document_review_open = True

    def open_review(self, content_digest: str) -> None:
        """Open the general lane for review, resetting its prior decision state."""
        self.approved = False
        self.approved_by = None
        self._expected_digest = content_digest
        self._review_open = True

    # Plan Review Signals (from architecture specification)
    @workflow.signal
    def approve_plan(self, *args: Any) -> None:
        """Approve research plan, proceed to execution.

        Takes ``(approver_id, content_digest)``. Requires an approver identity
        and a matching content digest while the plan review lane is open;
        any other input is a silent no-op.
        """
        _accept_approval(
            self,
            args,
            open_attr="_plan_review_open",
            digest_attr="_expected_plan_digest",
            approved_attr="plan_approved",
            approved_by_attr="plan_approved_by",
            feedback_received_attr="plan_feedback_received",
            feedback_comments_attr="plan_feedback_comments",
        )

    @workflow.signal
    def provide_plan_feedback(self, *args: Any) -> None:
        """Request plan revision with feedback.

        Takes ``(approver_id, comments)``. Requires an approver identity;
        any other input is a silent no-op.
        """
        # STIG V-222612: bound stored comment; signals must not raise.
        _accept_feedback(
            self,
            args,
            received_attr="plan_feedback_received",
            comments_attr="plan_feedback_comments",
            approved_attr="plan_approved",
        )

    # Document Review Signals (from architecture specification)
    @workflow.signal
    def approve_research(self, *args: Any) -> None:
        """Approve final document.

        Takes ``(approver_id, content_digest)``. Requires an approver identity
        and a matching content digest while the document review lane is open;
        any other input is a silent no-op.
        """
        _accept_approval(
            self,
            args,
            open_attr="_document_review_open",
            digest_attr="_expected_document_digest",
            approved_attr="document_approved",
            approved_by_attr="document_approved_by",
            feedback_received_attr="document_feedback_received",
            feedback_comments_attr="document_feedback_comments",
        )

    @workflow.signal
    def provide_feedback(self, *args: Any) -> None:
        """Request document revision with feedback.

        Takes ``(approver_id, comments)``. Requires an approver identity;
        any other input is a silent no-op.
        """
        # STIG V-222612: bound stored comment; signals must not raise.
        _accept_feedback(
            self,
            args,
            received_attr="document_feedback_received",
            comments_attr="document_feedback_comments",
            approved_attr="document_approved",
        )

    # General workflow control
    @workflow.signal
    def approve(self, *args: Any) -> None:
        """General approval signal.

        Takes ``(approver_id, content_digest)``. Requires an approver identity
        and a matching content digest while the general review lane is open;
        any other input is a silent no-op.
        """
        _accept_approval(
            self,
            args,
            open_attr="_review_open",
            digest_attr="_expected_digest",
            approved_attr="approved",
            approved_by_attr="approved_by",
        )

    @workflow.signal
    def cancel_workflow(self, *args: Any) -> None:
        """Cancel the entire workflow.

        Takes ``(approver_id,)``. Requires exactly one non-empty approver
        identity string; any other input is a silent no-op.
        """
        if len(args) != 1 or not isinstance(args[0], str) or not args[0]:
            return
        (approver_id,) = args
        self.cancelled = True
        self.cancelled_by = approver_id

    # Helper methods for workflow logic
    def reset_plan_feedback(self) -> None:
        """Reset plan feedback state for next iteration"""
        self.plan_feedback_received = False
        self.plan_feedback_comments = ""

    def reset_document_feedback(self) -> None:
        """Reset document feedback state for next iteration"""
        self.document_feedback_received = False
        self.document_feedback_comments = ""

    def is_plan_decision_received(self) -> bool:
        """Check if any plan decision (approve or feedback) was received"""
        return self.plan_approved or self.plan_feedback_received

    def is_document_decision_received(self) -> bool:
        """Check if any document decision (approve or feedback) was received"""
        return self.document_approved or self.document_feedback_received


# Signal builder functions for custom workflows
def create_approval_signal(signal_name: str = "approve"):
    """
    Create a custom approval signal bound to an approver identity and a
    content digest, following the same binding as HILSignalsMixin.

    The generated signal is accepted only while its review lane is open
    (opened via ``open_approval_review``) and the supplied digest matches;
    otherwise it is a silent no-op (signal handlers must not raise). The
    generated signal takes ``(approver_id, content_digest)``; any other
    argument count or type is also a silent no-op.

    Args:
        signal_name: Name of the signal method

    Returns:
        Workflow signal decorator
    """
    approved_attr = _approval_attribute_name(signal_name)
    approved_by_attr = f"{approved_attr}_by"
    open_attr = f"_{signal_name}_review_open"
    digest_attr = f"_expected_{signal_name}_digest"

    def signal_func(self, *args: Any) -> None:
        _accept_approval(
            self,
            args,
            open_attr=open_attr,
            digest_attr=digest_attr,
            approved_attr=approved_attr,
            approved_by_attr=approved_by_attr,
        )

    signal_func.__name__ = signal_name
    return workflow.signal(signal_func)


def open_approval_review(instance, signal_name: str, content_digest: str) -> None:
    """
    Open the review lane for a signal created by ``create_approval_signal``.

    Call this with the digest of the content now open for review before the
    generated signal will be accepted. Resets that signal's prior approval
    decision before the new digest becomes active.

    Args:
        instance: the workflow instance the generated signal is bound to
        signal_name: the same name passed to create_approval_signal
        content_digest: digest of the content now open for review
    """
    approved_attr = _approval_attribute_name(signal_name)
    setattr(instance, approved_attr, False)
    setattr(instance, f"{approved_attr}_by", None)
    setattr(instance, f"_expected_{signal_name}_digest", content_digest)
    setattr(instance, f"_{signal_name}_review_open", True)


def create_feedback_signal(signal_name: str = "provide_feedback"):
    """
    Create a custom feedback signal bound to an approver identity, following
    the same binding as HILSignalsMixin's feedback signals.

    The generated signal takes ``(approver_id, comments)``. It is a silent
    no-op without an approver or with any other argument count, including a
    legacy comments-only call (signal handlers must not raise).

    Args:
        signal_name: Name of the signal method

    Returns:
        Workflow signal decorator
    """
    base_name = signal_name.replace("provide_", "")
    received_attr = f"{base_name}_received"
    comments_attr = f"{base_name}_comments"

    def signal_func(self, *args: Any) -> None:
        # STIG V-222612: bound stored comment; signals must not raise.
        _accept_feedback(
            self,
            args,
            received_attr=received_attr,
            comments_attr=comments_attr,
        )

    signal_func.__name__ = signal_name
    return workflow.signal(signal_func)
