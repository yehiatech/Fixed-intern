import os
from dotenv import load_dotenv

from vonage import Auth, Vonage
from vonage_voice import CreateCallRequest, Phone, ToPhone

load_dotenv()

APPLICATION_ID = os.environ["VONAGE_APPLICATION_ID"]
PRIVATE_KEY = os.environ["VONAGE_PRIVATE_KEY"]

FROM_NUMBER = os.environ["VONAGE_NUMBER"]
TO_NUMBER = os.environ["TO_NUMBER"]

# Your public HTTPS URL
PUBLIC_URL = os.environ["PUBLIC_URL"]


client = Vonage(
    Auth(
        application_id=APPLICATION_ID,
        private_key=PRIVATE_KEY,
    )
)

CUSTOMER_NAME = "سما"  

response = client.voice.create_call(
    CreateCallRequest(
        to=[
            ToPhone(number="201212759267")
        ],
        from_=Phone(number="12345678901"),
        ncco=[ 
    { 
        "action": "talk", 
        "text": f"أهلاً {CUSTOMER_NAME}، هل تم حل المشكلة اللي كنت بتواصلت بخصوصها؟", 
        "language": "ar", 
        "bargeIn": False  # يسمح لك بالرد فوراً
    }, 
    { 
        
        "action": "input", 
        "type": ["speech"], 
        "speech": { 
            "language": "ar-EG", 
            "endOnSilence": 2, 
            "maxDuration": 30 
        }, 
        "eventUrl": [f"{PUBLIC_URL}/webhooks/speech"], 
        "eventMethod": "POST" 
    } 
]
    )
)
print("Call created successfully!")
print(response)