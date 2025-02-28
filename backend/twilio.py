# Create a file twilio.py inside your project directory for Twilio API credentials

# settings.py
import os
from decouple import config
from rest_framework_simplejwt.settings import api_settings as jwt_settings

class TwilioSettings:
    """
    Settings for integrating with the Twilio API for sending SMS messages.
    """

    account_sid = config("TWILIO_ACCOUNT_SID", default="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    """Twilio Account SID: Required for authentication with the Twilio API. 
       Can be found on the Twilio website in your account dashboard.
    """

    auth_token = config("TWILIO_AUTH_TOKEN", default="your_auth_token")
    """Twilio Auth Token: Needed for authentication with the Twilio API.
       Visible on the Twilio website in your account dashboard. Keep this secure.
    """

    phone_number = config("TWILIO_PHONE_NUMBER", default="+1234567890")
    """Twilio Phone Number: The Twilio phone number you will use to send SMS messages.
       This number must be purchased and verified through Twilio.
    """

twilio_settings = TwilioSettings()