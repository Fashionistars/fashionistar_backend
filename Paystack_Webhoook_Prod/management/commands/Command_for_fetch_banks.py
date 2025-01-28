from django.core.management.base import BaseCommand
import requests
import json
from django.conf import settings
import os

def fetch_paystack_banks():
    """
    Fetches a list of banks from the Paystack API and stores it as a JSON file.
    """
    url = "https://api.paystack.co/bank"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        bank_list = response.json()['data']
        
        # Path to save the bank list json file in the project directory
        project_dir = os.path.dirname(os.path.abspath(__file__)) # Get current directory
        json_path = os.path.join(project_dir, 'banks.json')
        with open(json_path, 'w') as file:
            json.dump(bank_list, file, indent=4)
        print("Bank list fetched and saved to banks.json.")
    except requests.exceptions.RequestException as e:
         # Log the error message and raise the error
        application_logger.error(f"Error fetching banks from paystack api: {e}")
        raise Exception(f"Error fetching banks from paystack api: {e}")
    except Exception as e:
        application_logger.error(f"Error saving paystack bank list: {e}")
        raise Exception(f"Error saving paystack bank list: {e}")









class Command(BaseCommand):
   help = "Fetches and stores the list of banks from paystack api"

   def handle(self, *args, **options):
      try:
         fetch_paystack_banks()
         self.stdout.write(self.style.SUCCESS('Successfully fetched and stored bank list.'))
      except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to fetch bank list: {e}'))