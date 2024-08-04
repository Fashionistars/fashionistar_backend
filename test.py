
# from Crypto.Cipher import DES3
# from Crypto.Util.Padding import pad
# import base64

# def encrypt_3des(key, data):
#     cipher = DES3.new(key.encode('utf-8'), DES3.MODE_ECB)
#     padded_data = pad(data.encode('utf-8'), DES3.block_size)
#     encrypted_data = cipher.encrypt(padded_data)
#     return base64.b64encode(encrypted_data).decode('utf-8')

# import requests
# import json

# # Set the URL for the request
# url = "https://api.flutterwave.com/v3/charges?type=card"

# # Define your encryption key
# encryption_key = "FLWSECK_TESTa005c6a95ea6"  


# payload = {
#     "card_number": "5061460410120223210",
#     "cvv": "470",
#     "expiry_month": "09",
#     "expiry_year": "32",
#     "amount": "10",
#     "email": "belovedvince@gmail.com",
#     "currency": "NGN",
#     "phonenumber": "07085572785",
#     "firstname": "temi",
#     "lastname": "desola",
#     "IP": "355426087298442",
#     "tx_ref": "MC-1720368606237",
#     "usesecureauth": True,
#     "preauthorize": False,
#     # "authorization": {
#     #     "mode": "pin",
#     #     "pin": "3310"
#     # }
# }

# # Convert the payload to a string and encrypt it
# payload_str = json.dumps(payload)
# encrypted_payload = encrypt_3des(encryption_key, payload_str)

# # Define the headers
# headers = {
#     "Authorization": "Bearer FLWSECK_TEST-7ec46444d9ede5c450740457bf804f77-X",
#     "Content-Type": "application/json"
# }

# # Define the data with the encrypted payload
# data = {
#     "client": encrypted_payload
# }

# # Make the POST request
# response = requests.post(url, headers=headers, json=data)

# # Print the response
# print(response.json())


# # import requests

# # # Define the flw_ref from the initial charge response
# # flw_ref = response.json().get('data', {}).get('flw_ref')
# # print(f"flw_ref: {flw_ref}")

# # # Set the URL for the request
# # url_new = f"https://api.flutterwave.com/v3/charges/{flw_ref}/capture"

# # # Define the body parameters
# # new_payload = {
# #     "amount": "10", # Amount to capture
# # }

# # def new_encrypt_3des(key, data):
# #     cipher = DES3.new(key.encode('utf-8'), DES3.MODE_ECB)
# #     padded_data = pad(data.encode('utf-8'), DES3.block_size)
# #     encrypted_data = cipher.encrypt(padded_data)
# #     return base64.b64encode(encrypted_data).decode('utf-8')

# # new_payload_str = json.dumps(new_payload)
# # print(new_payload_str)
# # new_encrypted_payload = new_encrypt_3des(encryption_key, new_payload_str)
# # # Make the POST request

# # new_data = {
# #     "client": new_encrypted_payload
# # }
# # new_response = requests.post(url_new, headers=headers, json=new_payload)

# # # Print the response
# # print(new_response.json())
