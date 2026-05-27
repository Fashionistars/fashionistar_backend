# apps/client/admin_backend/services.py
import logging
from django.db import transaction
from apps.client.services.client_profile_service import ClientProfileService
from apps.client.models.client_profile import ClientProfile

logger = logging.getLogger(__name__)

class AdminClientService:
    @staticmethod
    @transaction.atomic
    def update_client_profile(profile_id: str, data: dict, admin_user) -> ClientProfile:
        """
        Update client profile as an admin.
        """
        profile = ClientProfile.objects.select_for_update().get(pk=profile_id)
        user = profile.user
        
        # Call core update_profile service
        updated_profile = ClientProfileService.update_profile(user=user, data=data)
        
        logger.info("Admin %s updated client profile %s", admin_user.email, profile_id)
        return updated_profile
