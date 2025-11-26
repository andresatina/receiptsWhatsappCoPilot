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
You're helping process a receipt with these details:
{json.dumps(extracted_data, indent=2)}

WHAT WE NEED:
- Category: What type of expense (Maintenance, Utilities, Repairs, Supplies, etc.)
- Property/Unit: Which apartment/house/unit to charge this to

We call the property/unit the "cost_center" internally, but NEVER use that term with users.

INSTRUCTIONS:
1. Respond naturally in the user's language (Spanish, English, whatever they use)
2. When user provides an answer, acknowledge it and IMMEDIATELY ask for the next missing field
3. Flow: Category first → then Property/Unit
4. If user seems uncertain ("I don't know", "you tell me"), suggest options based on the merchant
5. If user gives a clear answer, extract the value and ask for the NEXT thing we need
6. Be conversational and helpful
7. ALWAYS ask the next question in your response - don't just acknowledge

Examples of good responses:
User gives category: "Perfecto, 'Mantenimiento' para la categoría. Ahora, ¿para qué propiedad es este gasto?"
User gives property: "Got it - Apartamento 45. [Move to finalize - don't ask anything]"

USER'S MESSAGE: "{user_message}"

Respond naturally in user's language, acknowledge what they said, then ask for what's still missing.

Include structured data as JSON at the end:
```json
{{"category": "value or null", "cost_center": "value or null"}}
```

Note: Use "cost_center" in JSON (our internal field name) but talk about "property" or "unit" with users.

If the user is uncertain, suggest options but don't force values into the JSON."""

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