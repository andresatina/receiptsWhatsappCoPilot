import requests

class WhatsAppHandler:
    def __init__(self, api_key, phone_number):
        self.api_key = api_key
        self.phone_number = phone_number
        self.phone_number_id = "820178674522656"
    
    def send_message(self, to_number, message):
        """Send text message via WhatsApp using Kapso's Meta API proxy"""
        url = "https://app.kapso.ai/api/meta/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }
        
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        params = {
            "phone_number_id": self.phone_number_id
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, params=params)
            print(f"Send message response status: {response.status_code}")
            print(f"Send message response: {response.text}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error sending message: {str(e)}")
            raise