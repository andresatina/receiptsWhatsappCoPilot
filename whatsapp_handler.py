import requests

class WhatsAppHandler:
    def __init__(self, api_key, phone_number):
        self.api_key = api_key
        self.phone_number = phone_number
    
    def send_message(self, to_number, message):
        """Send text message via WhatsApp using Kapso API"""
        url = "https://app.kapso.ai/api/v1/whatsapp_messages"
        
        payload = {
            "whatsapp_message": {
                "phone": to_number,
                "message_type": "text",
                "text": {
                    "body": message
                }
            }
        }
        
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            print(f"Send message response status: {response.status_code}")
            print(f"Send message response: {response.text}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error sending message: {str(e)}")
            raise