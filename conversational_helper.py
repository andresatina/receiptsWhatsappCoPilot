"""
Conversational Handler with Memory and Learning
"""

import os
import anthropic
import json


class ConversationalHandler:
    """Handles conversation with memory and learning capabilities"""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    
    def get_conversational_response(self, user_message, conversation_state):
        """
        Get natural response from Claude with full conversation history
        
        Args:
            user_message: What the user just said
            conversation_state: Full state with history and learned patterns
        
        Returns:
            dict with 'response' and 'extracted_data'
        """
        
        # Get conversation history and learned patterns
        conversation_history = conversation_state.get('conversation_history', [])
        learned_patterns = conversation_state.get('learned_patterns', {})
        extracted_data = conversation_state.get('extracted_data', {})
        
        # Build system prompt with personality + learned patterns
        system_prompt = self._build_system_prompt(conversation_state, learned_patterns, extracted_data)
        
        # Add current message to history
        conversation_history.append({
            'role': 'user',
            'content': user_message
        })
        
        # Keep last 10 messages for context (prevent token bloat)
        conversation_history = conversation_history[-10:]
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                system=system_prompt,
                messages=conversation_history
            )
            
            response_text = response.content[0].text
            
            # Extract JSON if present
            extracted = self._extract_json(response_text)
            
            # Clean response (remove JSON)
            clean_response = self._clean_response(response_text)
            
            # Add assistant response to history
            conversation_history.append({
                'role': 'assistant',
                'content': clean_response
            })
            
            # Update conversation state
            conversation_state['conversation_history'] = conversation_history
            
            return {
                'response': clean_response,
                'extracted_data': extracted or {}
            }
            
        except Exception as e:
            print(f"Error in conversational response: {str(e)}")
            return {
                'response': "Sorry, I'm having trouble. Can you try again?",
                'extracted_data': {}
            }
    
    def _build_system_prompt(self, conversation_state, learned_patterns, extracted_data):
        """Build system prompt with personality, context, and learned patterns"""
        
        # Get current state
        state_type = conversation_state.get('state', 'new')
        last_msg = conversation_state.get('last_system_message', '')
        merchant = extracted_data.get('merchant_name', '').lower()
        
        # Build learned patterns context
        patterns_text = ""
        if learned_patterns and merchant and merchant in learned_patterns:
            pattern = learned_patterns[merchant]
            patterns_text = f"""
LEARNED PATTERNS for {merchant}:
- Last time you used: Category="{pattern.get('category')}", Property="{pattern.get('property')}"
- Suggest these same values to the user, but let them change if needed"""
        
        # Build situation context
        situation_text = self._build_situation_context(conversation_state, last_msg, extracted_data)
        
        return f"""You are Atina, an AI controller assistant for property managers.

PERSONALITY:
- Competent and direct - you get things done
- Friendly but professional - nice, but command respect
- Subtle wit - smart humor, not corny
- Confident - you know what you're doing

{patterns_text}

CURRENT SITUATION:
{situation_text}

INSTRUCTIONS:
1. ALWAYS respond in the user's language (detect from conversation history)
2. Maintain the same language throughout the entire conversation
3. When processing a receipt:
   - Ask for category first (Maintenance, Utilities, Repairs, Supplies, etc.)
   - Then ask for property/unit (NEVER say "cost center" - say "property" or "unit" or "apartment")
   - If you have learned patterns, suggest them: "Last time you used X for this merchant. Use that again?"
   - If user is uncertain, suggest options based on merchant
4. When receipt is saved, provide summary and encourage another
5. For greetings when no receipt sent, ask them to send a receipt photo

If you need structured data (category, property), include JSON at the END:
```json
{{"category": "value or null", "cost_center": "value or null"}}
```

Note: Use "cost_center" in JSON (our internal field) but say "property" or "unit" when talking to users."""
    
    def _build_situation_context(self, conversation_state, last_msg, extracted_data):
        """Build context based on current state"""
        state_type = conversation_state.get('state', 'new')
        
        if state_type == 'new':
            return "User just greeted you or hasn't sent a receipt. Ask them to send a receipt photo."
        
        elif '[User just sent a receipt image' in last_msg:
            return "User just sent receipt. Tell them briefly you're processing it (like 'Processing...'). Keep it short."
        
        elif '[Tell user you\'re saving' in last_msg:
            return "Tell user briefly you're saving the receipt (like 'Saving...'). Keep it very short."
        
        elif '[Receipt processed]' in last_msg:
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            
            return f"""Processing receipt: {merchant} for ${amount}
Category: {'✅ Have it' if has_category else '❌ Need to ask'}
Property: {'✅ Have it' if has_cost_center else '❌ Need to ask'}

Ask for what's missing. If you have learned patterns for this merchant, suggest them!"""
        
        elif '[Receipt saved successfully]' in last_msg:
            data = extracted_data
            return f"""Receipt saved! Provide summary:
• Merchant: {data.get('merchant_name')}
• Amount: ${data.get('total_amount')}
• Category: {data.get('category')}
• Property: {data.get('cost_center')}
Encourage them to send another receipt."""
        
        elif '[User sent a duplicate receipt]' in last_msg:
            return "User sent duplicate receipt. Ask if they want to process it anyway."
        
        elif '[Error' in last_msg:
            return "Error occurred. Apologize and ask them to try again."
        
        elif '[User confirmed duplicate' in last_msg:
            return "User confirmed duplicate. Tell them briefly you're processing it."
        
        else:
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            return f"""Processing receipt.
Category: {'✅' if has_category else '❌ Need it'}
Property: {'✅' if has_cost_center else '❌ Need it'}
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
            json_start = text.rfind('{')
            if json_start > len(text) * 0.6:
                return text[:json_start].strip()
        return text


# Global instance
conversational = ConversationalHandler()