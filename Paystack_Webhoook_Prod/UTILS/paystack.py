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
        def __init__(self, amount=None, currency="NGN", recipient_code=None,reason=None):
            self.reference = str(set_ref())
            if amount:
              self.amount = str(int(amount) * 100)
            self.currency = str(currency)
            self.recipient_code = recipient_code
            self.reason = reason
        


        def initiate_transfer(self):
            '''
            Initiate a transfer from your Paystack balance
            '''
            url = "https://api.paystack.co/transfer"
            transfer_data = {
               "source": "balance",
                "reason": self.reason,
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







