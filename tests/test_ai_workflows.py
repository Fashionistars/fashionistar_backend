# tests/test_ai_workflows.py
"""
Unit tests for FASHIONISTAR AI LangGraph Workflows:
- MeasurementWorkflow
- RecommendationWorkflow
"""

import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.ai.workflows.measurement import MeasurementWorkflow
from apps.ai.workflows.recommendation import RecommendationWorkflow
from apps.measurements.models.scan import BodyScanSession
from apps.measurements.models import MeasurementProfile

User = get_user_model()


class AIWorkflowsTests(TestCase):
    """Verify that both workflows compile and run successfully."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="ai_workflow_user@fashionistar.test",
            password="SecurePass123!",
            role="client",
        )
        # Create a body scan session
        self.session = BodyScanSession.objects.create(
            owner=self.user,
            device_type="web",
            scan_provider="ai_camera",
            status="pending",
        )
        # Mock the geometry pipeline run
        self.mock_geometry_result = {
            "is_valid": True,
            "validation_message": "Success",
            "quality_score": 0.85,
            "profile_fields": {
                "height": 175.0,
                "chest": 95.0,
                "waist": 80.0,
                "hips": 98.0,
                "shoulder_width": 45.0,
            },
            "linear": {
                "height": 175.0,
                "shoulder_width": 45.0,
            },
            "circumferences": {
                "chest": 95.0,
                "waist": 80.0,
                "hips": 98.0,
            }
        }

    @patch("apps.ai.utils.geometry.run_full_measurement_pipeline")
    @patch("apps.ai.tasks.recommendation_tasks.run_profile_recommendations.delay")
    def test_measurement_workflow_success(self, mock_rec_task, mock_pipeline):
        """MeasurementWorkflow runs, saves profile, and completes session."""
        mock_pipeline.return_value = self.mock_geometry_result

        # Run workflow
        workflow = MeasurementWorkflow()
        result = workflow.execute({
            "session_id": str(self.session.session_id),
            "user_id": self.user.id,
            "user_height_cm": 175.0,
            "user_weight_kg": 70.0,
            "landmarks": [{"x": 0.1, "y": 0.2, "z": 0.3} for _ in range(33)],
        })

        # Assertions
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["quality_score"], 0.85)
        self.assertEqual(result["errors"], [])

        # Check DB updates
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")
        self.assertEqual(self.session.scan_confidence, 0.85)

        # Check MeasurementProfile created
        profile = MeasurementProfile.objects.filter(owner=self.user).first()
        self.assertIsNotNone(profile)
        self.assertEqual(profile.height, 175.0)

        # Check recommendation task was fired
        mock_rec_task.assert_called_once_with(
            profile_id=str(profile.id),
            user_id=self.user.id,
        )

    def test_recommendation_workflow_empty_candidates(self):
        """RecommendationWorkflow handles early exit elegantly when no candidates exist."""
        # Create a measurement profile for the user
        profile = MeasurementProfile.objects.create(
            owner=self.user,
            height=175.0,
            bust=95.0,
            waist=80.0,
            hips=98.0,
        )

        workflow = RecommendationWorkflow()
        result = workflow.execute({
            "profile_id": str(profile.id),
            "user_id": self.user.id,
        })

        # Assertions (should complete with empty recommendations since candidate pool is empty)
        self.assertEqual(result["recommendation_ids"], [])
        self.assertEqual(result["errors"], [])
