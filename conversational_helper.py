"""
Simple Conversational Handler - Adds natural conversation to existing receipt flow
"""

import os
import anthropic
import json


class ConversationalHandler:
    """Handles natural conversation while preserving existing receipt flow"""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    
    def get_conversational_response(self, user_message, conversation_state, whatsapp_handler):
        """
        Get natural response from Claude based on full context
        
        Args:
            user_message: What the user just said
            conversation_state: Current state dict from conversation_states
            whatsapp_handler: To get user's conversation history if needed
        
        Returns:
            dict with:
                'response': What to send to user
                'extracted_data': Any structured data Claude extracted (category, cost_center, etc.)
        """
        
        # Build context for Claude
        extracted_data = conversation_state.get('extracted_data', {})
        current_question = conversation_state.get('current_question', '')
        
        # Determine what we need
        has_category = bool(extracted_data.get('category'))
        has_cost_center = bool(extracted_data.get('cost_center'))
        
        # Build system prompt
        system_prompt = f"""You are Atina, an AI controller assistant for property managers.

PERSONALITY:
- Competent and direct - you get things done
- Friendly but professional - nice, but command respect
- Subtle wit - smart humor, not corny
- Confident - you know what you're doing

CURRENT SITUATION:
{self._build_situation_context(conversation_state)}

INSTRUCTIONS:
1. ALWAYS respond in the user's language (detect from their messages)
2. Be conversational and natural
3. When processing a receipt:
   - Ask for category first (Maintenance, Utilities, Repairs, Supplies, etc.)
   - Then ask for property/unit (NEVER say "cost center")
   - If user is uncertain, suggest options based on merchant
4. When receipt is saved, provide a summary and encourage them to send another
5. Handle errors gracefully
6. For greetings when no receipt sent yet, ask them to send a receipt photo

USER'S MESSAGE: "{user_message}"

Respond naturally in the user's language. If you need structured data, include JSON at the end:
```json
{{"category": "value or null", "cost_center": "value or null"}}
```"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            
            response_text = response.content[0].text
            
            # Extract JSON if present
            extracted = self._extract_json(response_text)
            
            # Clean response (remove JSON)
            clean_response = self._clean_response(response_text)
            
            return {
                'response': clean_response,
                'extracted_data': extracted or {}
            }
            
        except Exception as e:
            print(f"Error in conversational response: {str(e)}")
            # Fallback to simple parsing
            return {
                'response': f"Got it. Continuing...",
                'extracted_data': {current_question: user_message} if current_question else {}
            }
    
    def _build_situation_context(self, conversation_state):
        """Build context description based on current state"""
        state_type = conversation_state.get('state', 'new')
        extracted_data = conversation_state.get('extracted_data', {})
        
        if state_type == 'new':
            return "User just greeted you. They haven't sent a receipt yet. Ask them to send a receipt photo to get started."
        
        elif '[Receipt processed:' in conversation_state.get('last_system_message', ''):
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            
            return f"""You're processing a receipt:
Merchant: {merchant}
Amount: ${amount}
Date: {extracted_data.get('date', 'Unknown')}

What we have:
- Category: {'✅ ' + extracted_data.get('category') if has_category else '❌ Need to ask'}
- Property/Unit: {'✅ ' + extracted_data.get('cost_center') if has_cost_center else '❌ Need to ask'}

Ask for what's missing. Category first, then property/unit."""
        
        elif '[Receipt saved successfully]' in conversation_state.get('last_system_message', ''):
            data = extracted_data
            return f"""Receipt was just saved successfully!
Provide a friendly summary and encourage them to send another receipt.

Summary to share:
• Merchant: {data.get('merchant_name', 'N/A')}
• Amount: ${data.get('total_amount', 'N/A')}
• Category: {data.get('category', 'N/A')}
• Property: {data.get('cost_center', 'N/A')}
• Saved to Google Sheets"""
        
        elif '[User sent a duplicate receipt]' in conversation_state.get('last_system_message', ''):
            return "User sent a duplicate receipt. Ask if they want to process it anyway."
        
        elif '[Error' in conversation_state.get('last_system_message', ''):
            return "There was an error. Apologize and ask them to try again or send a clearer photo."
        
        else:
            # General case - processing receipt
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            
            return f"""Processing receipt for {extracted_data.get('merchant_name', 'unknown merchant')}.
Category: {'✅ Have it' if has_category else '❌ Need it'}
Property: {'✅ Have it' if has_cost_center else '❌ Need it'}

Ask for what's missing."""
    
    def _extract_json(self, text):
        """Extract JSON from response"""
        try:
            if '```json' in text:
                start = text.find('```json') + 7
                end = text.find('```', start)
                json_str = text[start:end].strip()
                return json.loads(json_str)
            elif '{' in text and '}' in text:
                start = text.rfind('{')
                json_str = text[start:].strip()
                return json.loads(json_str)
        except:
            pass
        return None
    
    def _clean_response(self, text):
        """Remove JSON blocks from response"""
        if '```json' in text:
            return text[:text.find('```json')].strip()
        elif '{' in text and '}' in text:
            # Check if JSON is at the end
            json_start = text.rfind('{')
            if json_start > len(text) * 0.6:  # JSON in last 40%
                return text[:json_start].strip()
        return text


# Global instance
conversational = ConversationalHandler()