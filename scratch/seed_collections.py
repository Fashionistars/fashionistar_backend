import requests

login_url = "http://localhost:8001/api/v1/auth/login/"
create_url = "http://localhost:8001/api/v1/admin_backend/catalog/collections/create/"

# Login
payload = {
    "email_or_phone": "admin@fashionistar.io",
    "password": "FashionAdmin2026!"
}
r = requests.post(login_url, json=payload)
r.raise_for_status()
access_token = r.json()["data"]["access"]

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

collections = [
    {
        "title": "Street Couture",
        "sub_title": "Urban runway streetwear.",
        "description": "Modern prints and designer sportswear inspired by the streets of Lagos."
    },
    {
        "title": "Corporate Chic",
        "sub_title": "Office and formal kaftans.",
        "description": "Breathable linen, tailored kaftans, and sharp senators for business and formal settings."
    },
    {
        "title": "Kids Kingdom",
        "sub_title": "Children traditional wears.",
        "description": "Miniature agbadas, kaftans, and cute dashikis for the little ones."
    },
    {
        "title": "Agbada Royale",
        "sub_title": "Regal ceremonial agbadas.",
        "description": "Heavy embroidery, premium fabrics, and royal cuts designed for society weddings."
    }
]

for c in collections:
    res = requests.post(create_url, json=c, headers=headers)
    print(f"Status: {res.status_code}, Title: {c['title']}, Response: {res.json()}")
