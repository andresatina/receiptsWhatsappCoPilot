"""
Conversational Handler with Memory and Learning - IMPROVED UX
"""

import os
import anthropic
import json


class ConversationalHandler:
    """Handles conversation with memory and learning capabilities"""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    
    def get_conversational_response(self, user_message, conversation_state, is_system_message=False):
        """
        Get natural response from Claude with full conversation history
        
        Args:
            user_message: What the user just said
            conversation_state: Full state with history and learned patterns
            is_system_message: If True, this is a system directive (not actual user text)
        
        Returns:
            dict with 'response' and 'extracted_data'
        """
        
        # Get conversation history and learned patterns
        conversation_history = conversation_state.get('conversation_history', [])
        learned_patterns = conversation_state.get('learned_patterns', {})
        extracted_data = conversation_state.get('extracted_data', {})
        
        # Determine max_tokens based on context
        max_tokens = self._get_token_limit(conversation_state)
        
        # Build system prompt with personality + learned patterns
        system_prompt = self._build_system_prompt(conversation_state, learned_patterns, extracted_data)
        
        # Only add to conversation history if not a system message
        if not is_system_message:
            conversation_history.append({
                'role': 'user',
                'content': user_message
            })
        else:
            # For system messages, treat as instruction without adding to user history
            # We'll handle this by injecting context directly into the system prompt
            system_prompt += f"\n\nIMMEDIATE ACTION: {user_message}"
        
        # Keep last 10 messages for context (prevent token bloat)
        conversation_history = conversation_history[-10:]
        
        try:
            # Build appropriate message list
            if conversation_history:
                messages_to_send = conversation_history
            elif is_system_message:
                # For system messages with no history, create a minimal exchange
                messages_to_send = [
                    {"role": "user", "content": "Hola"},
                    {"role": "assistant", "content": "Hola! ¿Cómo puedo ayudarte?"}
                ]
            else:
                messages_to_send = [{"role": "user", "content": user_message}]
            
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages_to_send
            )
            
            # Debug logging
            print(f"Claude API Response - Stop reason: {response.stop_reason}")
            print(f"Content blocks: {len(response.content) if response.content else 0}")
            
            # Handle empty responses
            if not response.content or len(response.content) == 0:
                print("ERROR: Claude returned empty response")
                return {
                    'response': "Procesando..." if 'processing' in str(conversation_state.get('last_system_message', '')).lower() else "Un momento...",
                    'extracted_data': {}
                }
            
            response_text = response.content[0].text
            
            # Extract JSON if present
            extracted = self._extract_json(response_text)
            
            # Clean response (remove JSON)
            clean_response = self._clean_response(response_text)
            
            # Add assistant response to history (only if not system message)
            if not is_system_message:
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
            print(f"Error type: {type(e).__name__}")
            print(f"System prompt length: {len(system_prompt) if 'system_prompt' in locals() else 'N/A'}")
            print(f"Messages count: {len(messages_to_send) if 'messages_to_send' in locals() else 'N/A'}")
            import traceback
            traceback.print_exc()
            return {
                'response': "Disculpa, tengo problemas. ¿Puedes intentar de nuevo?",
                'extracted_data': {}
            }
    
    def _get_token_limit(self, conversation_state):
        """Determine appropriate token limit based on context"""
        last_msg = conversation_state.get('last_system_message', '')
        
        # Short responses for most interactions
        if '[Receipt saved successfully]' in last_msg:
            return 300  # Summary needs more space
        elif '[Receipt processed]' in last_msg:
            return 150  # Just asking for category
        elif 'processing' in last_msg.lower():
            return 50   # Just "Procesando..."
        else:
            return 200  # Default for follow-ups
    
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
LEARNED PATTERN for {merchant}:
- Previously: Category="{pattern.get('category')}", Property="{pattern.get('property')}"
- Suggest briefly: "Last time: {pattern.get('category')} / {pattern.get('property')}. Same?"
"""
        
        # Build situation context
        situation_text = self._build_situation_context(conversation_state, last_msg, extracted_data)
        
        return f"""You are Atina, an AI receipt assistant for property managers.

PERSONALITY:
- Direct and concise - get to the point fast
- Friendly but efficient - no fluff
- Keep responses under 2 sentences unless providing final summary

{patterns_text}

CURRENT SITUATION:
{situation_text}

RESPONSE RULES:
1. Respond in user's language (Spanish/English based on their messages)
2. Keep same language throughout conversation
3. Be brief - max 2 sentences per message (except final summary)
4. Don't explain options unless user asks
5. When asking for category: list 3-5 options in bullet points, nothing more
6. When asking for property: just ask "¿Qué propiedad?" or "Which property?"
7. Accept user's answer immediately - don't confirm unless unclear
8. Use "propiedad" or "apartamento" in Spanish, "property" or "unit" in English (NEVER "cost center")

STRUCTURED DATA:
Return JSON only when user provides category or property:
```json
{{"category": "value or null", "cost_center": "value or null"}}
```

Note: Use "cost_center" in JSON (internal field) but say "property/unit" to users."""
    
    def _build_situation_context(self, conversation_state, last_msg, extracted_data):
        """Build concise context based on current state"""
        state_type = conversation_state.get('state', 'new')
        
        if state_type == 'new':
            return "User greeted or no receipt sent. Ask for receipt photo (1 sentence)."
        
        elif '[User just sent a receipt image' in last_msg:
            return "Say 'Procesando...' or 'Processing...' in user's language. Nothing else."
        
        elif '[Tell user you\'re saving' in last_msg:
            return "Say 'Guardando...' or 'Saving...' in user's language. Nothing else."
        
        elif '[Receipt processed]' in last_msg:
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            
            if has_category and has_cost_center:
                return "Already have both category and property. This shouldn't happen - just acknowledge."
            elif has_category:
                return f"Have category. Ask ONLY for property: '¿Qué propiedad?' (nothing else)"
            elif has_cost_center:
                return f"Have property. Ask ONLY for category with 3-5 options in bullets"
            else:
                return f"Receipt: {merchant}, ${amount}. Ask for category with 3-5 options in bullets. If learned pattern exists, suggest it first."
        
        elif '[Receipt saved successfully]' in last_msg:
            data = extracted_data
            return f"""Provide summary (max 4 lines):
✅ {data.get('merchant_name')} - ${data.get('total_amount')}
• Categoría: {data.get('category')}
• Propiedad: {data.get('cost_center')}
Ask if they have another receipt (1 sentence)."""
        
        elif '[User sent a duplicate receipt]' in last_msg:
            return "Duplicate detected. Ask briefly if they want to process anyway."
        
        elif '[Error' in last_msg:
            return "Error occurred. Apologize briefly, ask to try again."
        
        elif '[User confirmed duplicate' in last_msg:
            return "Say 'Procesando...' Nothing else."
        
        else:
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            
            if not has_category:
                return "Ask for category with 3-5 options in bullets. Be brief."
            elif not has_cost_center:
                return "Ask for property: '¿Qué propiedad?' (1 sentence)"
            else:
                return "Have both. This shouldn't happen."
    
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