import anthropic
import base64
import json

class ClaudeHandler:
    def __init__(self, api_key):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
    
    def extract_receipt_data(self, image_data):
        """Extract structured data from receipt image using Claude"""
        
        # Convert image to base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        prompt = """Analyze this receipt image and extract the following information in JSON format:

{
  "merchant_name": "name of the business",
  "date": "date in YYYY-MM-DD format",
  "total_amount": "total amount as number (no currency symbols)",
  "payment_method": "payment method if visible (e.g., Cash, Credit Card, Debit)",
  "line_items": [
    {
      "description": "item name",
      "amount": "item cost as number"
    }
  ]
}

IMPORTANT:
- Only include fields you can clearly read from the receipt
- For total_amount, extract just the number without $ or other symbols
- If a field is unclear or not visible, use null
- Be accurate with the merchant name and date

Return ONLY valid JSON, no other text."""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )
        
        # Parse JSON response
        response_text = message.content[0].text
        
        # Clean up response (remove markdown code blocks if present)
        response_text = response_text.strip()
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
        response_text = response_text.strip()
        
        extracted_data = json.loads(response_text)
        
        # Auto-categorize based on merchant name
        category = self._auto_categorize(extracted_data.get('merchant_name', ''))
        if category:
            extracted_data['category'] = category
        
        return extracted_data
    
    def _auto_categorize(self, merchant_name):
        """Auto-categorize expense based on merchant name"""
        merchant_lower = merchant_name.lower()
        
        # Simple categorization logic
        if any(word in merchant_lower for word in ['restaurant', 'cafe', 'coffee', 'pizza', 'burger', 'food', 'diner', 'bistro']):
            return 'Meals & Entertainment'
        elif any(word in merchant_lower for word in ['uber', 'lyft', 'taxi', 'airline', 'hotel', 'airbnb']):
            return 'Travel'
        elif any(word in merchant_lower for word in ['office', 'depot', 'staples', 'supply']):
            return 'Office Supplies'
        elif any(word in merchant_lower for word in ['gas', 'fuel', 'shell', 'chevron', 'exxon']):
            return 'Transportation'
        elif any(word in merchant_lower for word in ['amazon', 'best buy', 'target', 'walmart']):
            return 'General Supplies'
        
        return None
    
    def update_with_user_response(self, extracted_data, question_field, user_response):
        """Update extracted data with user's text response"""
        
        prompt = f"""Given this receipt data:
{json.dumps(extracted_data, indent=2)}

The user was asked about: {question_field}
Their response: {user_response}

Update the JSON with this information. Return ONLY the updated JSON, no other text."""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        response_text = message.content[0].text.strip()
        
        # Clean up response
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
        response_text = response_text.strip()
        
        try:
            updated_data = json.loads(response_text)
            return updated_data
        except:
            # If parsing fails, manually update the field
            extracted_data[question_field] = user_response
            return extracted_data
