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
    
    def get_conversational_response(self, user_message, conversation_state):
        """
        Get natural response from Claude with full conversation history
        
        Args:
            user_message: What the user just said (or system directive)
            conversation_state: Full state with history and learned patterns
        
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
        
        # Add current message to history
        conversation_history.append({
            'role': 'user',
            'content': user_message
        })
        
        # Keep last 10 messages for context (prevent token bloat)
        conversation_history = conversation_history[-10:]
        
        # CRITICAL: Filter out messages with empty content (Claude API requirement)
        # Empty messages cause: "messages.X: all messages must have non-empty content"
        conversation_history = [
            msg for msg in conversation_history 
            if msg.get('content', '').strip()
        ]
        
        # Debug: Log conversation history to identify issues
        print(f"📝 Conversation history ({len(conversation_history)} messages):")
        for i, msg in enumerate(conversation_history):
            content_preview = msg.get('content', '')[:50]
            print(f"  {i}: {msg.get('role')} - {content_preview}...")
        
        # Ensure we have at least one message
        if not conversation_history:
            conversation_history = [{'role': 'user', 'content': user_message}]
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=conversation_history
            )
            
            # Debug logging
            print(f"Claude API Response - Stop reason: {response.stop_reason}")
            print(f"Content blocks: {len(response.content) if response.content else 0}")
            
            # Handle empty responses
            if not response.content or len(response.content) == 0:
                print("ERROR: Claude returned empty response")
                return {
                    'response': "Processing...",
                    'extracted_data': {}
                }
            
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
            print(f"Error type: {type(e).__name__}")
            print(f"System prompt length: {len(system_prompt) if 'system_prompt' in locals() else 'N/A'}")
            print(f"Messages count: {len(messages_to_send) if 'messages_to_send' in locals() else 'N/A'}")
            import traceback
            traceback.print_exc()
            return {
                'response': "Sorry, I'm having issues. Can you try again?",
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
            return 50   # Just "Processing..."
        else:
            return 200  # Default for follow-ups
    
    def _build_system_prompt(self, conversation_state, learned_patterns, extracted_data):
        """Build system prompt with personality, context, and patterns"""
        
        # Get current state
        state_type = conversation_state.get('state', 'new')
        last_msg = conversation_state.get('last_system_message', '')
        suggested_pattern = conversation_state.get('suggested_pattern')
        
        # Build pattern suggestion context
        if suggested_pattern:
            patterns_text = f"""
            PATTERN MATCH FOUND ({suggested_pattern['similarity']:.0f}% similarity):
                - Previously used: Category="{suggested_pattern['category']}", Cost Center="{suggested_pattern['cost_center']}"
                - ASK IMMEDIATELY: "Last time you used '{suggested_pattern['category']}' for this merchant. Use the same?"
                - DO NOT list category options - just ask for confirmation
                - If user says yes/same/correct, extract the suggested category immediately
                - Only if user says no, then show 2-3 suggestions and ask what category they want instead
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
1. Match the user's language naturally throughout the conversation
2. Be brief - max 3 sentences per message (except final summary)
3. When asking for category: list 1-2 options in bullet points
4. When asking for property: just ask directly for the property/unit
5. Accept user's answer immediately - don't confirm unless unclear


STRUCTURED DATA:
When user provides category or property, include JSON for data extraction:
```json
{{"category": "value or null", "cost_center": "value or null"}}
```

CRITICAL: The JSON is for internal data extraction ONLY. Users must NEVER see the JSON.
Always include your conversational response BEFORE any JSON.
Example: "Which property is this for?" (user sees this)
{{JSON here}} (system extracts this, user never sees it)

Note: Use "cost_center" in JSON (internal field) but say "property/unit" to users."""
    
    def _build_situation_context(self, conversation_state, last_msg, extracted_data):
        """Build concise context based on current state"""
        state_type = conversation_state.get('state', 'new')
        
        if state_type == 'new':
            return "User greeted or no receipt sent. Ask for receipt photo (1 sentence)."
        
        elif '[User just sent a receipt image' in last_msg:
            return "Tell user you're processing the receipt. Keep it brief - just one or two words in their language."
        
        elif '[Tell user you\'re saving' in last_msg:
            return "Tell user you're saving the receipt. Keep it brief - just one or two words in their language."
        
        elif '[Receipt processed' in last_msg:
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            
            if has_category and has_cost_center:
                return "Already have both category and property. This shouldn't happen - just acknowledge."
            elif has_category:
                return f"Receipt: {merchant}, ${amount}. Have category already. Ask ONLY for property unit/apartment (nothing else)"
            elif has_cost_center:
                return f"Receipt: {merchant}, ${amount}. Have property already. Ask ONLY for category with 2-3 options in bullets"
            else:
                return f"Receipt: {merchant}, ${amount}. Ask for category with 2-3 merchant-appropriate options in bullets. If learned pattern exists, suggest it first."
        
        elif '[Receipt saved successfully]' in last_msg:
            data = extracted_data
            return f"""IMPORTANT: You MUST provide a complete summary in this exact format:

✅ Receipt saved successfully!

Details:
• Merchant: {data.get('merchant_name', 'Unknown')}
• Amount: ${data.get('total_amount', '0.00')}
• Category: {data.get('category', 'Unknown')}
• Property: {data.get('cost_center', 'Unknown')}

Then ask: "Do you have another receipt to process?" """
        
        elif '[User sent a duplicate receipt]' in last_msg:
            return "Duplicate detected. Ask briefly if they want to process anyway."
        
        elif '[Error' in last_msg:
            return "Error occurred. Apologize briefly, ask to try again."
        
        elif '[User confirmed duplicate' in last_msg:
            return "Tell user you're processing the receipt. Keep it brief."
        
        else:
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            
            if not has_category:
                return "Ask for category with 2-3 options in bullets. Be brief."
            elif not has_cost_center:
                return "Ask for property/unit (1 sentence)"
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
        """Remove ALL JSON blocks from response - user should never see JSON"""
        import re
        
        # Remove ```json blocks (with any content inside, including newlines)
        text = re.sub(r'```json\s*\n.*?\n```', '', text, flags=re.DOTALL)
        text = re.sub(r'```json.*?```', '', text, flags=re.DOTALL)
        
        # Remove standalone {...} objects anywhere in text
        # This catches both {"key": "value"} and multi-line JSON
        text = re.sub(r'\{[^{}]*\}', '', text)
        
        # Clean up extra whitespace and newlines left behind
        text = re.sub(r'\n\s*\n+', '\n\n', text)  # Multiple newlines → double newline
        
        cleaned = text.strip()
        
        # CRITICAL: Never return empty string (causes Claude API errors)
        if not cleaned or not cleaned.strip():
            return "..."  # Safe neutral fallback
        
        return cleaned


# Global instance
conversational = ConversationalHandler()