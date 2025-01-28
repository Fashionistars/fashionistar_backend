'''
Paystack payment file
'''
import secrets
import requests
from backend.settings import PAYSTACK_TEST_KEY, PAYSTACK_SECRET_KEY


HEADERS = {
    "Authorization": "Bearer "+ PAYSTACK_SECRET_KEY,
}


def set_ref():
    '''
    Create reference code
    '''
    return secrets.token_urlsafe()


class Transaction:
    '''
    The Transactions API allows you create and manage payments on your integration
    '''
    def __init__(self, email=None, amount=None, currency="NGN",):
        self.reference = str(set_ref())
        if amount:
            self.amount = str(int(amount) * 100)
        self.currency = str(currency)
        if email:
          self.email = str(email)
        self.body = {
            "email": email,
            "amount": self.amount,
            "reference": self.reference,
            "currency": self.currency,
            "channels": ["bank", "card", "ussd", "mobile_money", "bank_transfer", "qr"]
        }
    

    def initialize_transaction(self):
        '''
        Initialize a transaction from your backend
        '''
        url = "https://api.paystack.co/transaction/initialize"
        res = requests.post(url, headers=HEADERS, data=self.body)
        return res.json()



class Transfer:
        '''
        The Transactions API allows you create and manage payments on your integration
        '''
        def __init__(self, amount=None, currency="NGN", recipient_code=None,):
            self.reference = str(set_ref())
            if amount:
              self.amount = str(int(amount) * 100)
            self.currency = str(currency)
            self.recipient_code = recipient_code
        


        def initiate_transfer(self):
            '''
            Initiate a transfer from your Paystack balance
            '''
            url = "https://api.paystack.co/transfer"
            transfer_data = {
               "source": "balance",
                "reason": "Withdrawal",
                "amount": self.amount,
                "recipient": self.recipient_code,
             }
            # Log the request data
            print('transfer_data',transfer_data)
            try:
                res = requests.post(url, headers=HEADERS, json=transfer_data)
                res.raise_for_status()
                return res.json()
            except requests.exceptions.RequestException as e:
                if 'res' in locals():
                    if res.status_code == 500:
                        print(f"Paystack 500 Error: {e}, response: {res.text}")
                        return {
                            "status": False,
                            "message": f"Paystack 500 Error: {e}, response: {res.text}",
                            "meta": {'nextStep': 'Try again later'},
                            "type": 'server_error',
                            "code": 'paystack_500',
                        }
                    else:
                        print(f"Error from paystack API: {e}, response: {res.text if 'res' in locals() else None}")
                        return {
                            "status": False,
                            "message": f"Failed to transfer funds: {e}, response: {res.text if 'res' in locals() else None}",
                            "meta": {'nextStep': 'Try again later'},
                            "type": 'api_error',
                            "code": 'unknown',
                        }
                else:
                    print(f"Error from paystack API: {e}")
                    return {
                       "status": False,
                       "message": f"Failed to transfer funds: {e}",
                        "meta": {'nextStep': 'Try again later'},
                        "type": 'api_error',
                        "code": 'unknown',
                    }











class TransferRecipient:
    '''
     Used to handle transfer recipient functionality
    '''
    def __init__(self,  recipient_account_number=None, recipient_name=None, bank_code=None):
        self.recipient_account_number = recipient_account_number
        self.recipient_name = recipient_name
        self.bank_code = bank_code


    def create_transfer_recipient(self):
         '''
         Create a transfer recipient
         '''
         url = "https://api.paystack.co/transferrecipient"
         transfer_recipient_data = {
             "type": "nuban",
             "name": self.recipient_name,
             "account_number": self.recipient_account_number,
             "bank_code": self.bank_code,
             "currency": "NGN"
         }
         try:
            res = requests.post(url, headers=HEADERS, json=transfer_recipient_data)
            res.raise_for_status()
            return res.json()
         except requests.exceptions.RequestException as e:
            if 'res' in locals():
                print(f"Error creating transfer recipient: {e}, response: {res.text}")
                return {
                    "status": False,
                    "message": f"Error creating transfer recipient: {e}, response: {res.text}",
                    "meta": {'nextStep': 'Try again later'},
                    "type": 'api_error',
                    "code": 'unknown',
                }
            else:
                 print(f"Error from paystack API: {e}")
                 return {
                    "status": False,
                    "message": f"Failed to create transfer recipient: {e}",
                    "meta": {'nextStep': 'Try again later'},
                    "type": 'api_error',
                     "code": 'unknown',
                    }





    def update_transfer_recipient(self, recipient_code, recipient_data):
        '''
        This function is used to update a paystack transfer recipient.
        '''
        url = f"https://api.paystack.co/transferrecipient/{recipient_code}"
        headers = {
                "Authorization": "Bearer "+ settings.PAYSTACK_SECRET_KEY,
                'Content-Type': 'application/json'
            }
        try:
            res = requests.put(url, data=json.dumps(recipient_data), headers=headers)
            res.raise_for_status()
            return res.json()
        except requests.exceptions.RequestException as e:
            paystack_logger.error(f"Failed to update transfer recipient, paystack error: {e}")
            return {"status": False, "message": f"Failed to update transfer recipient: {e}"}





    def delete_transfer_recipient(self, recipient_code):
        '''
        This function is used to delete a paystack transfer recipient.
        '''
        url = f"https://api.paystack.co/transferrecipient/{recipient_code}"
        headers = {
                "Authorization": "Bearer "+ settings.PAYSTACK_SECRET_KEY,
            }
        try:
            res = requests.delete(url, headers=headers)
            res.raise_for_status()
            return res.json()
        except requests.exceptions.RequestException as e:
            paystack_logger.error(f"Failed to delete transfer recipient, paystack error: {e}")
            return {"status": False, "message": f"Failed to delete transfer recipient: {e}"}



    def fetch_transfer_recipient(self, recipient_code):
        """
        Fetch details for a transfer recipient.
        """
        url = f"https://api.paystack.co/transferrecipient/{recipient_code}"
        try:
            res = requests.get(url, headers=HEADERS)
            res.raise_for_status()
            return res.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching transfer recipient: {e}, response: {res.text if 'res' in locals() else None}")
            return {
                "status": False,
                "message": f"Error fetching transfer recipient: {e}, response: {res.text if 'res' in locals() else None}",
                "meta": {'nextStep': 'Try again later'},
                "type": 'api_error',
                "code": 'unknown',
            }
    














class Refund:
    '''
    Authorize refunds.
    '''
    def __init__(self, reference):
        self.body = {
            "transaction": reference
        }

    def create_refund(self):
        url = 'https://api.paystack.co/refund'
        res = requests.post(url, data=self.body, headers=HEADERS)
        return res.json()



def verify_payment(reference):
    '''
    Confirm the status of a transaction.
    '''
    url = "https://api.paystack.co/transaction/verify/"+ reference
    res = requests.get(url, headers=HEADERS)
    return res.json()



def get_transaction_detail(transaction_id):
    '''
    Get details of a transaction carried out on your integration.
    '''
    url = "https://api.paystack.co/transaction/" + transaction_id
    res = requests.get(url, headers=HEADERS)
    return res.json()



def get_transaction_timeline(transaction_id):
    '''
    View the timeline of a transaction
    '''
    url = "https://api.paystack.co/transaction/timeline/" + transaction_id
    res = requests.get(url, headers=HEADERS)
    return res.json()







