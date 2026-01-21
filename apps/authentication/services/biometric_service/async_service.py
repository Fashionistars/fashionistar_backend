# apps/authentication/services/biometric_service/async_service.py

import logging
import asyncio
from fido2.server import Fido2Server
from fido2.webauthn import UserVerificationRequirement, AuthenticatorAttachment
from django.conf import settings
from apps.authentication.models import BiometricCredential, UnifiedUser

logger = logging.getLogger('application')

# FIDO2 Server Initialization (Shared config)
RP_ID = getattr(settings, 'FIDO2_RP_ID', 'localhost')
RP_NAME = getattr(settings, 'FIDO2_RP_NAME', 'Fashionistar')
server = Fido2Server(
    {"id": RP_ID, "name": RP_NAME},
    verify_origin=lambda x: True
)

class AsyncBiometricService:
    """
    Asynchronous Service for WebAuthn / FIDO2 Authentication.
    """

    @staticmethod
    async def generate_registration_options(user: UnifiedUser):
        try:
            # Native Async Query
            credentials = [c async for c in BiometricCredential.objects.filter(user=user)]
            
            exclude_list = [
                {"type": "public-key", "id": cred.credential_id} for cred in credentials
            ]

            user_data = {
                "id": str(user.id).encode('utf-8'),
                "name": user.email or str(user.phone),
                "displayName": f"{user.first_name} {user.last_name}".strip() or "User"
            }

            # Offload heavy/crypto logic
            options, state = await asyncio.to_thread(
                server.register_begin,
                user_data,
                credentials=exclude_list,
                user_verification=UserVerificationRequirement.PREFERRED,
                authenticator_attachment=AuthenticatorAttachment.PLATFORM
            )
            return options, state
        except Exception as e:
            logger.error(f"❌ Biometric Reg Options Error (Async): {e}")
            raise Exception("Failed to generate biometric options.")

    @staticmethod
    async def verify_registration_response(user: UnifiedUser, response_data, state, device_name="Unknown"):
        try:
            # Offload crypto verification
            auth_data = await asyncio.to_thread(server.register_complete, state, response_data)

            # Native Async Save
            await BiometricCredential.objects.acreate(
                user=user,
                credential_id=auth_data.credential_data.credential_id,
                public_key=auth_data.credential_data.public_key,
                sign_count=auth_data.sign_count,
                device_name=device_name
            )
            
            logger.info(f"✅ Biometric Credential Registered for {user.email} (Async)")
            return True
        except Exception as e:
            logger.error(f"❌ Biometric Reg Verify Error (Async): {e}")
            raise Exception("Invalid biometric data.")

    @staticmethod
    async def generate_auth_options(user: UnifiedUser):
        try:
            credentials = [c async for c in BiometricCredential.objects.filter(user=user)]
            if not credentials:
                raise Exception("No biometric credentials found.")

            allow_list = [
                {"type": "public-key", "id": cred.credential_id} for cred in credentials
            ]

            options, state = await asyncio.to_thread(
                server.authenticate_begin,
                allow_list,
                user_verification=UserVerificationRequirement.PREFERRED
            )
            return options, state
        except Exception as e:
            logger.error(f"❌ Biometric Auth Options Error (Async): {e}")
            raise

    @staticmethod
    async def verify_auth_response(user: UnifiedUser, response_data, state):
        try:
            credentials = [c async for c in BiometricCredential.objects.filter(user=user)]
            if not credentials:
                 raise Exception("No credentials.")

            # Offload verification
            # Passing list of model instances; assumes fido2 library can read attributes or we need to map them
            # Fido2Server.authenticate_complete handles lists of (credential_id, public_key, sign_count, etc)
            # Our model objects have the attributes.
            await asyncio.to_thread(
                server.authenticate_complete,
                state,
                credentials,
                response_data
            )
            
            logger.info(f"✅ Biometric Login Success: {user.email} (Async)")
            return True
        except Exception as e:
            logger.error(f"❌ Biometric Auth Verify Error (Async): {e}")
            raise Exception("Biometric authentication failed.")
