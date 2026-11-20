# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.signals module"""

import hashlib

from foundry_temporal._limits import MAX_SIGNAL_COMMENT_LENGTH
from foundry_temporal.signals import (
    HILSignalsMixin,
    create_approval_signal,
    create_feedback_signal,
    open_approval_review,
)

PLAN_DIGEST = hashlib.sha256(b"plan content").hexdigest()
DOC_DIGEST = hashlib.sha256(b"document content").hexdigest()
GENERAL_DIGEST = hashlib.sha256(b"general content").hexdigest()
OTHER_DIGEST = hashlib.sha256(b"other content").hexdigest()


class TestHILSignalsMixin:
    def test_init_default_state(self):
        """Test HILSignalsMixin initialization with default state"""
        mixin = HILSignalsMixin()

        # Plan review state
        assert mixin.plan_approved is False
        assert mixin.plan_approved_by is None
        assert mixin.plan_feedback_received is False
        assert mixin.plan_feedback_comments == ""

        # Document review state
        assert mixin.document_approved is False
        assert mixin.document_approved_by is None
        assert mixin.document_feedback_received is False
        assert mixin.document_feedback_comments == ""

        # General state
        assert mixin.approved is False
        assert mixin.approved_by is None
        assert mixin.cancelled is False
        assert mixin.cancelled_by is None

    # approve_plan requires identity, digest, and an open review lane

    def test_approve_plan_signal_accepted_with_identity_and_matching_digest(self):
        """Test approve_plan signal is accepted when open, identified, and digest-matched"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)
        mixin.plan_feedback_received = True
        mixin.plan_feedback_comments = "Some feedback"

        mixin.approve_plan("reviewer-1", PLAN_DIGEST)

        assert mixin.plan_approved is True
        assert mixin.plan_approved_by == "reviewer-1"
        assert mixin.plan_feedback_received is False
        assert mixin.plan_feedback_comments == ""

    def test_approve_plan_signal_rejected_without_approver_id(self):
        """An approve_plan signal with no approver identity is a silent no-op"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)

        mixin.approve_plan("", PLAN_DIGEST)

        assert mixin.plan_approved is False
        assert mixin.plan_approved_by is None

    def test_approve_plan_signal_rejected_with_wrong_digest(self):
        """An approve_plan signal with a mismatched content digest is a silent no-op"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)

        mixin.approve_plan("reviewer-1", OTHER_DIGEST)

        assert mixin.plan_approved is False
        assert mixin.plan_approved_by is None

    def test_approve_plan_signal_rejected_with_non_ascii_digest(self):
        """A non-ASCII content digest is a silent no-op, not a TypeError"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)

        mixin.approve_plan("reviewer-1", "é" * 64)

        assert mixin.plan_approved is False
        assert mixin.plan_approved_by is None

    def test_approve_plan_signal_rejected_with_lone_surrogate_digest(self):
        """A digest with a lone surrogate is a silent no-op, not a UnicodeEncodeError"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)

        mixin.approve_plan("reviewer-1", "\ud800")

        assert mixin.plan_approved is False
        assert mixin.plan_approved_by is None

    def test_approve_plan_signal_rejected_with_non_ascii_expected_digest(self):
        """A lane opened with a non-ASCII digest never accepts an approval"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review("\ud800")

        mixin.approve_plan("reviewer-1", PLAN_DIGEST)

        assert mixin.plan_approved is False
        assert mixin.plan_approved_by is None

    def test_approve_plan_signal_rejected_with_wrong_argument_count(self):
        """Zero, one, or three arguments are a silent no-op, not a TypeError"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)

        mixin.approve_plan()
        mixin.approve_plan("reviewer-1")
        mixin.approve_plan("reviewer-1", PLAN_DIGEST, "extra")

        assert mixin.plan_approved is False
        assert mixin.plan_approved_by is None

    def test_approve_plan_signal_rejected_before_review_opened(self):
        """An approve_plan signal received before the review lane opens is a silent no-op"""
        mixin = HILSignalsMixin()

        mixin.approve_plan("reviewer-1", PLAN_DIGEST)

        assert mixin.plan_approved is False

    def test_approve_plan_signal_rejected_after_review_closed(self):
        """A second approve_plan signal after the lane already closed does not change the recorded decision"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)
        mixin.approve_plan("reviewer-1", PLAN_DIGEST)
        assert mixin.plan_approved is True

        mixin.approve_plan("reviewer-2", PLAN_DIGEST)

        assert mixin.plan_approved_by == "reviewer-1"

    def test_open_plan_review_resets_prior_decision(self):
        """Opening a new plan review clears the prior approval before accepting new signals"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)
        mixin.approve_plan("reviewer-1", PLAN_DIGEST)
        assert mixin.plan_approved is True

        mixin.open_plan_review(OTHER_DIGEST)

        assert mixin.plan_approved is False
        assert mixin.plan_approved_by is None
        assert mixin.plan_feedback_received is False
        assert mixin.plan_feedback_comments == ""

        mixin.approve_plan("reviewer-2", OTHER_DIGEST)
        assert mixin.plan_approved is True
        assert mixin.plan_approved_by == "reviewer-2"

    def test_provide_plan_feedback_signal(self):
        """Test provide_plan_feedback signal"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)
        mixin.approve_plan("reviewer-1", PLAN_DIGEST)
        assert mixin.plan_approved is True

        feedback_comments = "Please revise the approach"
        mixin.provide_plan_feedback("reviewer-2", feedback_comments)

        assert mixin.plan_feedback_received is True
        assert mixin.plan_feedback_comments == feedback_comments
        assert mixin.plan_approved is False

    def test_provide_plan_feedback_rejected_without_approver_id(self):
        """A provide_plan_feedback signal with no approver identity is a silent no-op"""
        mixin = HILSignalsMixin()

        mixin.provide_plan_feedback("", "feedback")

        assert mixin.plan_feedback_received is False
        assert mixin.plan_feedback_comments == ""

    # approve_research requires identity, digest, and an open review lane

    def test_approve_research_signal_accepted_with_identity_and_matching_digest(self):
        """Test approve_research signal is accepted when open, identified, and digest-matched"""
        mixin = HILSignalsMixin()
        mixin.open_document_review(DOC_DIGEST)
        mixin.document_feedback_received = True
        mixin.document_feedback_comments = "Some feedback"

        mixin.approve_research("reviewer-1", DOC_DIGEST)

        assert mixin.document_approved is True
        assert mixin.document_approved_by == "reviewer-1"
        assert mixin.document_feedback_received is False
        assert mixin.document_feedback_comments == ""

    def test_approve_research_signal_rejected_with_wrong_digest(self):
        """An approve_research signal with a mismatched content digest is a silent no-op"""
        mixin = HILSignalsMixin()
        mixin.open_document_review(DOC_DIGEST)

        mixin.approve_research("reviewer-1", OTHER_DIGEST)

        assert mixin.document_approved is False
        assert mixin.document_approved_by is None

    def test_approve_research_signal_rejected_before_review_opened(self):
        """An approve_research signal received before the review lane opens is a silent no-op"""
        mixin = HILSignalsMixin()

        mixin.approve_research("reviewer-1", DOC_DIGEST)

        assert mixin.document_approved is False

    def test_provide_feedback_signal(self):
        """Test provide_feedback signal (for documents)"""
        mixin = HILSignalsMixin()
        mixin.open_document_review(DOC_DIGEST)
        mixin.approve_research("reviewer-1", DOC_DIGEST)
        assert mixin.document_approved is True

        feedback_comments = "Please add more details"
        mixin.provide_feedback("reviewer-2", feedback_comments)

        assert mixin.document_feedback_received is True
        assert mixin.document_feedback_comments == feedback_comments
        assert mixin.document_approved is False

    def test_provide_feedback_rejected_without_approver_id(self):
        """A provide_feedback signal with no approver identity is a silent no-op"""
        mixin = HILSignalsMixin()

        mixin.provide_feedback("", "feedback")

        assert mixin.document_feedback_received is False
        assert mixin.document_feedback_comments == ""

    def test_provide_feedback_with_none_comments_does_not_raise(self):
        """A provide_feedback signal with None comments records an empty comment"""
        mixin = HILSignalsMixin()

        mixin.provide_feedback("reviewer-1", None)  # pyright: ignore[reportArgumentType]

        assert mixin.document_feedback_received is True
        assert mixin.document_feedback_comments == ""

    def test_provide_feedback_legacy_comments_only_is_noop(self):
        """A legacy comments-only call is a no-op; its text is never read as an approver"""
        mixin = HILSignalsMixin()

        mixin.provide_feedback("please revise")

        assert mixin.document_feedback_received is False
        assert mixin.document_feedback_comments == ""

    # general approve requires identity, digest, and an open review lane

    def test_general_approve_signal_accepted_with_identity_and_matching_digest(self):
        """Test general approve signal is accepted when open, identified, and digest-matched"""
        mixin = HILSignalsMixin()
        mixin.open_review(GENERAL_DIGEST)

        mixin.approve("reviewer-1", GENERAL_DIGEST)

        assert mixin.approved is True
        assert mixin.approved_by == "reviewer-1"

    def test_general_approve_signal_rejected_before_review_opened(self):
        """A general approve signal received before the review lane opens is a silent no-op"""
        mixin = HILSignalsMixin()

        mixin.approve("reviewer-1", GENERAL_DIGEST)

        assert mixin.approved is False

    def test_general_approve_signal_rejected_with_wrong_digest(self):
        """A general approve signal with a mismatched content digest is a silent no-op"""
        mixin = HILSignalsMixin()
        mixin.open_review(GENERAL_DIGEST)

        mixin.approve("reviewer-1", OTHER_DIGEST)

        assert mixin.approved is False
        assert mixin.approved_by is None

    def test_general_approve_signal_rejected_without_approver_id(self):
        """A general approve signal with no approver identity is a silent no-op"""
        mixin = HILSignalsMixin()
        mixin.open_review(GENERAL_DIGEST)

        mixin.approve("", GENERAL_DIGEST)

        assert mixin.approved is False
        assert mixin.approved_by is None

    # cancel_workflow requires an approver identity

    def test_cancel_workflow_signal(self):
        """Test cancel_workflow signal"""
        mixin = HILSignalsMixin()

        assert mixin.cancelled is False

        mixin.cancel_workflow("reviewer-1")

        assert mixin.cancelled is True
        assert mixin.cancelled_by == "reviewer-1"

    def test_cancel_workflow_signal_rejected_without_approver_id(self):
        """A cancel_workflow signal with no approver identity is a silent no-op"""
        mixin = HILSignalsMixin()

        mixin.cancel_workflow("")

        assert mixin.cancelled is False
        assert mixin.cancelled_by is None

    def test_cancel_workflow_signal_rejected_with_invalid_args(self):
        """No argument, two arguments, or a non-string approver is a silent no-op"""
        mixin = HILSignalsMixin()

        mixin.cancel_workflow()
        mixin.cancel_workflow("reviewer-1", "extra")
        mixin.cancel_workflow(None)

        assert mixin.cancelled is False
        assert mixin.cancelled_by is None

    def test_reset_plan_feedback(self):
        """Test reset_plan_feedback helper method"""
        mixin = HILSignalsMixin()

        # Set feedback state
        mixin.plan_feedback_received = True
        mixin.plan_feedback_comments = "Some feedback"

        # Reset feedback
        mixin.reset_plan_feedback()

        # Should clear feedback but not affect approval
        assert mixin.plan_feedback_received is False
        assert mixin.plan_feedback_comments == ""

    def test_reset_document_feedback(self):
        """Test reset_document_feedback helper method"""
        mixin = HILSignalsMixin()

        # Set feedback state
        mixin.document_feedback_received = True
        mixin.document_feedback_comments = "Some feedback"

        # Reset feedback
        mixin.reset_document_feedback()

        # Should clear feedback but not affect approval
        assert mixin.document_feedback_received is False
        assert mixin.document_feedback_comments == ""

    def test_is_plan_decision_received_approved(self):
        """Test is_plan_decision_received when plan is approved"""
        mixin = HILSignalsMixin()

        assert mixin.is_plan_decision_received() is False

        mixin.plan_approved = True
        assert mixin.is_plan_decision_received() is True

    def test_is_plan_decision_received_feedback(self):
        """Test is_plan_decision_received when feedback is received"""
        mixin = HILSignalsMixin()

        assert mixin.is_plan_decision_received() is False

        mixin.plan_feedback_received = True
        assert mixin.is_plan_decision_received() is True

    def test_is_plan_decision_received_both(self):
        """Test is_plan_decision_received when both approval and feedback are set"""
        mixin = HILSignalsMixin()

        mixin.plan_approved = True
        mixin.plan_feedback_received = True

        assert mixin.is_plan_decision_received() is True

    def test_is_document_decision_received_approved(self):
        """Test is_document_decision_received when document is approved"""
        mixin = HILSignalsMixin()

        assert mixin.is_document_decision_received() is False

        mixin.document_approved = True
        assert mixin.is_document_decision_received() is True

    def test_is_document_decision_received_feedback(self):
        """Test is_document_decision_received when feedback is received"""
        mixin = HILSignalsMixin()

        assert mixin.is_document_decision_received() is False

        mixin.document_feedback_received = True
        assert mixin.is_document_decision_received() is True

    def test_is_document_decision_received_both(self):
        """Test is_document_decision_received when both approval and feedback are set"""
        mixin = HILSignalsMixin()

        mixin.document_approved = True
        mixin.document_feedback_received = True

        assert mixin.is_document_decision_received() is True

    def test_plan_and_document_states_independent(self):
        """Test that plan and document states are independent"""
        mixin = HILSignalsMixin()
        mixin.open_plan_review(PLAN_DIGEST)
        mixin.open_document_review(DOC_DIGEST)

        # Approve plan
        mixin.approve_plan("reviewer-1", PLAN_DIGEST)
        assert mixin.plan_approved is True
        assert mixin.document_approved is False

        # Approve document
        mixin.approve_research("reviewer-2", DOC_DIGEST)
        assert mixin.plan_approved is True  # Still true
        assert mixin.document_approved is True

        # Provide plan feedback
        mixin.provide_plan_feedback("reviewer-3", "Plan feedback")
        assert mixin.plan_approved is False
        assert mixin.document_approved is True  # Unaffected

        # Provide document feedback
        mixin.provide_feedback("reviewer-4", "Document feedback")
        assert mixin.plan_feedback_received is True  # Unaffected
        assert mixin.document_approved is False

    def test_multiple_feedback_cycles(self):
        """Test multiple feedback cycles"""
        mixin = HILSignalsMixin()

        # First plan feedback cycle
        mixin.provide_plan_feedback("reviewer-1", "First feedback")
        assert mixin.plan_feedback_comments == "First feedback"
        assert mixin.plan_approved is False

        # Approve after feedback
        mixin.open_plan_review(PLAN_DIGEST)
        mixin.approve_plan("reviewer-2", PLAN_DIGEST)
        assert mixin.plan_approved is True
        assert mixin.plan_feedback_comments == ""

        # Second plan feedback cycle
        mixin.provide_plan_feedback("reviewer-3", "Second feedback")
        assert mixin.plan_feedback_comments == "Second feedback"
        assert mixin.plan_approved is False

    def test_signals_have_workflow_decorators(self):
        """Test that signal methods have workflow.signal decorators"""
        # Note: This is a meta-test to ensure decorators are applied
        # In actual usage, these would be checked by Temporal

        assert hasattr(HILSignalsMixin.approve_plan, "__temporal_signal_definition")
        assert hasattr(HILSignalsMixin.provide_plan_feedback, "__temporal_signal_definition")
        assert hasattr(HILSignalsMixin.approve_research, "__temporal_signal_definition")
        assert hasattr(HILSignalsMixin.provide_feedback, "__temporal_signal_definition")
        assert hasattr(HILSignalsMixin.cancel_workflow, "__temporal_signal_definition")
        assert hasattr(HILSignalsMixin.approve, "__temporal_signal_definition")

    def test_mixin_with_multiple_inheritance(self):
        """Test HILSignalsMixin works with multiple inheritance"""

        class BaseWorkflow:
            def __init__(self):
                self.base_initialized = True

        class TestWorkflow(HILSignalsMixin, BaseWorkflow):
            def __init__(self):
                super().__init__()
                self.test_initialized = True

        workflow = TestWorkflow()

        # Should have both base and mixin functionality
        assert workflow.base_initialized is True
        assert workflow.test_initialized is True
        assert hasattr(workflow, "plan_approved")
        assert hasattr(workflow, "approve_plan")

    def test_empty_feedback_comments(self):
        """Test behavior with empty feedback comments"""
        mixin = HILSignalsMixin()

        # Provide empty feedback
        mixin.provide_plan_feedback("reviewer-1", "")
        assert mixin.plan_feedback_received is True
        assert mixin.plan_feedback_comments == ""

        # Provide whitespace-only feedback
        mixin.provide_feedback("reviewer-2", "   ")
        assert mixin.document_feedback_received is True
        assert mixin.document_feedback_comments == "   "

    # STIG V-222612: signal comment length bounds

    def test_provide_plan_feedback_within_limit_unchanged(self):
        """A plan feedback comment at the limit is stored unchanged."""
        mixin = HILSignalsMixin()
        comment = "x" * MAX_SIGNAL_COMMENT_LENGTH

        mixin.provide_plan_feedback("reviewer-1", comment)

        assert mixin.plan_feedback_comments == comment

    def test_provide_plan_feedback_truncates_oversized(self):
        """An oversized plan feedback comment is truncated (workflow not failed)."""
        mixin = HILSignalsMixin()

        mixin.provide_plan_feedback("reviewer-1", "x" * (MAX_SIGNAL_COMMENT_LENGTH + 100))

        assert mixin.plan_feedback_received is True
        assert len(mixin.plan_feedback_comments) == MAX_SIGNAL_COMMENT_LENGTH

    def test_provide_feedback_truncates_oversized(self):
        """An oversized document feedback comment is truncated."""
        mixin = HILSignalsMixin()

        mixin.provide_feedback("reviewer-1", "y" * (MAX_SIGNAL_COMMENT_LENGTH + 1))

        assert mixin.document_feedback_received is True
        assert len(mixin.document_feedback_comments) == MAX_SIGNAL_COMMENT_LENGTH


class TestCreateApprovalSignal:
    def test_create_approval_signal_default_name(self):
        """Test creating approval signal with default name"""
        signal_func = create_approval_signal()

        assert signal_func.__name__ == "approve"

    def test_create_approval_signal_custom_name(self):
        """Test creating approval signal with custom name"""
        signal_func = create_approval_signal("confirm")

        assert signal_func.__name__ == "confirm"

    def test_accepted_with_identity_and_matching_digest_while_lane_open(self):
        """Generated signal is accepted when the lane is open, identified, and digest-matched"""
        signal_func = create_approval_signal("deployment")

        class MockSelf:
            pass

        mock_self = MockSelf()
        open_approval_review(mock_self, "deployment", OTHER_DIGEST)

        signal_func(mock_self, "reviewer-1", OTHER_DIGEST)

        # Predictable "<name>_approved" naming (not the old "deploymented" bug)
        assert mock_self.deployment_approved is True
        assert mock_self.deployment_approved_by == "reviewer-1"

    def test_rejected_without_approver_id(self):
        """A generated signal with no approver identity is a silent no-op"""
        signal_func = create_approval_signal("deployment")

        class MockSelf:
            pass

        mock_self = MockSelf()
        open_approval_review(mock_self, "deployment", OTHER_DIGEST)

        signal_func(mock_self, "", OTHER_DIGEST)

        assert mock_self.deployment_approved is False

    def test_rejected_with_wrong_digest(self):
        """A generated signal with a mismatched content digest is a silent no-op"""
        signal_func = create_approval_signal("deployment")

        class MockSelf:
            pass

        mock_self = MockSelf()
        open_approval_review(mock_self, "deployment", OTHER_DIGEST)

        signal_func(mock_self, "reviewer-1", GENERAL_DIGEST)

        assert mock_self.deployment_approved is False
        assert mock_self.deployment_approved_by is None

    def test_rejected_before_review_opened(self):
        """A generated signal received before the lane opens is a silent no-op"""
        signal_func = create_approval_signal("deployment")

        class MockSelf:
            pass

        mock_self = MockSelf()

        signal_func(mock_self, "reviewer-1", OTHER_DIGEST)

        assert getattr(mock_self, "deployment_approved", False) is False

    def test_rejected_after_review_closed(self):
        """A second signal after the lane already closed does not change the recorded decision"""
        signal_func = create_approval_signal("deployment")

        class MockSelf:
            pass

        mock_self = MockSelf()
        open_approval_review(mock_self, "deployment", OTHER_DIGEST)
        signal_func(mock_self, "reviewer-1", OTHER_DIGEST)
        assert mock_self.deployment_approved is True

        signal_func(mock_self, "reviewer-2", OTHER_DIGEST)

        assert mock_self.deployment_approved_by == "reviewer-1"

    def test_default_name_sets_approved_attribute(self):
        """The default signal_name="approve" keeps the plain "approved" attribute"""
        signal_func = create_approval_signal()

        class MockSelf:
            pass

        mock_self = MockSelf()
        open_approval_review(mock_self, "approve", GENERAL_DIGEST)

        signal_func(mock_self, "reviewer-1", GENERAL_DIGEST)

        assert mock_self.approved is True
        assert mock_self.approved_by == "reviewer-1"

    def test_create_approval_signal_is_workflow_signal(self):
        """Test that created approval signal has workflow.signal decorator"""
        signal_func = create_approval_signal()

        # Should be decorated with workflow.signal
        assert hasattr(signal_func, "__temporal_signal_definition")


class TestOpenApprovalReview:
    def test_resets_prior_decision(self):
        """Opening a new factory review lane clears the prior approval decision"""
        signal_func = create_approval_signal("deployment")

        class MockSelf:
            pass

        mock_self = MockSelf()
        open_approval_review(mock_self, "deployment", OTHER_DIGEST)
        signal_func(mock_self, "reviewer-1", OTHER_DIGEST)
        assert mock_self.deployment_approved is True

        open_approval_review(mock_self, "deployment", GENERAL_DIGEST)

        assert mock_self.deployment_approved is False
        assert mock_self.deployment_approved_by is None

        signal_func(mock_self, "reviewer-2", GENERAL_DIGEST)
        assert mock_self.deployment_approved is True
        assert mock_self.deployment_approved_by == "reviewer-2"


class TestCreateFeedbackSignal:
    def test_create_feedback_signal_default_name(self):
        """Test creating feedback signal with default name"""
        signal_func = create_feedback_signal()

        assert signal_func.__name__ == "provide_feedback"

        class MockSelf:
            pass

        mock_self = MockSelf()
        comments = "Test feedback"
        signal_func(mock_self, "reviewer-1", comments)

        # Should set feedback_received and feedback_comments attributes
        assert mock_self.feedback_received is True
        assert mock_self.feedback_comments == comments

    def test_create_feedback_signal_custom_name(self):
        """Test creating feedback signal with custom name"""
        signal_func = create_feedback_signal("provide_review")

        assert signal_func.__name__ == "provide_review"

        class MockSelf:
            pass

        mock_self = MockSelf()
        comments = "Review comments"
        signal_func(mock_self, "reviewer-1", comments)

        # Should set review_received and review_comments attributes
        assert mock_self.review_received is True
        assert mock_self.review_comments == comments

    def test_create_feedback_signal_rejected_without_approver_id(self):
        """A generated feedback signal with no approver identity is a silent no-op"""
        signal_func = create_feedback_signal("provide_review")

        class MockSelf:
            pass

        mock_self = MockSelf()
        signal_func(mock_self, "", "Review comments")

        assert getattr(mock_self, "review_received", False) is False

    def test_create_feedback_signal_name_processing(self):
        """Test that signal name processing works correctly"""
        # Should remove 'provide_' prefix when creating attribute names
        signal_func = create_feedback_signal("provide_plan_feedback")

        class MockSelf:
            pass

        mock_self = MockSelf()
        signal_func(mock_self, "reviewer-1", "test")

        # Should create plan_feedback_received and plan_feedback_comments
        assert mock_self.plan_feedback_received is True
        assert mock_self.plan_feedback_comments == "test"

    def test_create_feedback_signal_without_provide_prefix(self):
        """Test feedback signal name without 'provide_' prefix"""
        signal_func = create_feedback_signal("review")

        class MockSelf:
            pass

        mock_self = MockSelf()
        signal_func(mock_self, "reviewer-1", "review text")

        # Should use the name as-is when no 'provide_' prefix
        assert mock_self.review_received is True
        assert mock_self.review_comments == "review text"

    def test_create_feedback_signal_empty_comments(self):
        """Test feedback signal with empty comments"""
        signal_func = create_feedback_signal()

        class MockSelf:
            pass

        mock_self = MockSelf()
        signal_func(mock_self, "reviewer-1", "")

        assert mock_self.feedback_received is True
        assert mock_self.feedback_comments == ""

    def test_create_feedback_signal_overwrites_existing(self):
        """Test feedback signal overwrites existing attributes"""
        signal_func = create_feedback_signal()

        class MockSelf:
            def __init__(self):
                self.feedback_received = False
                self.feedback_comments = "old"

        mock_self = MockSelf()
        signal_func(mock_self, "reviewer-1", "new comments")

        assert mock_self.feedback_received is True
        assert mock_self.feedback_comments == "new comments"

    def test_create_feedback_signal_is_workflow_signal(self):
        """Test that created feedback signal has workflow.signal decorator"""
        signal_func = create_feedback_signal()

        # Should be decorated with workflow.signal
        assert hasattr(signal_func, "__temporal_signal_definition")

    def test_create_feedback_signal_truncates_oversized(self):
        """Builder-created feedback signal truncates oversized comments (STIG V-222612)."""
        signal_func = create_feedback_signal()

        class MockSelf:
            pass

        mock_self = MockSelf()
        signal_func(mock_self, "reviewer-1", "z" * (MAX_SIGNAL_COMMENT_LENGTH + 50))

        assert mock_self.feedback_received is True
        assert len(mock_self.feedback_comments) == MAX_SIGNAL_COMMENT_LENGTH
