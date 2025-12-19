import requests

class WhatsAppHandler:
    def __init__(self, api_key, phone_number, phone_number_id):
        self.api_key = api_key
        self.phone_number = phone_number
        self.phone_number_id = phone_number_id
    
    def send_message(self, to_number, message):
        """Send text message via WhatsApp using Kapso's Meta API proxy"""
        # Following Kapso's documentation exactly:
        # https://api.kapso.ai/meta/whatsapp/v24.0/{phone_number_id}/messages
        url = f"https://api.kapso.ai/meta/whatsapp/v24.0/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {
                "body": message
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
