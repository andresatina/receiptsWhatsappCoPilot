"""
Conversational Handler with Memory and Learning - IMPROVED UX
"""

import os
import anthropic
import json
import re


class ConversationalHandler:
    """Handles conversation with memory and learning capabilities"""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    
    def get_conversational_response(self, user_message, conversation_state):
        """
        Get natural response from Claude with full conversation history
        """
        
        conversation_history = conversation_state.get('conversation_history', [])
        learned_patterns = conversation_state.get('learned_patterns', {})
        extracted_data = conversation_state.get('extracted_data', {})
        
        max_tokens = self._get_token_limit(conversation_state)
        system_prompt = self._build_system_prompt(conversation_state, learned_patterns, extracted_data)
        
        conversation_history.append({
            'role': 'user',
            'content': user_message
        })
        
        # Filter out empty messages
        conversation_history = [
            msg for msg in conversation_history 
            if msg.get('content', '').strip()
        ]
        
        # Token-based truncation
        conversation_history = self._truncate_by_tokens(conversation_history, max_tokens=6000)
        
        # Debug logging
        print(f"📝 Conversation history ({len(conversation_history)} messages):")
        for i, msg in enumerate(conversation_history):
            content_preview = msg.get('content', '')[:50]
            print(f"  {i}: {msg.get('role')} - {content_preview}...")
        
        if not conversation_history:
            conversation_history = [{'role': 'user', 'content': user_message}]
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=conversation_history
            )
            
            print(f"Claude API Response - Stop reason: {response.stop_reason}")
            print(f"Content blocks: {len(response.content) if response.content else 0}")
            
            if not response.content or len(response.content) == 0:
                print("ERROR: Claude returned empty response")
                return {
                    'response': "Processing...",
                    'extracted_data': {}
                }
            
            response_text = response.content[0].text
            extracted = self._extract_json(response_text)
            clean_response = self._clean_response(response_text)
            
            conversation_history.append({
                'role': 'assistant',
                'content': clean_response
            })
            
            conversation_state['conversation_history'] = conversation_history
            
            return {
                'response': clean_response,
                'extracted_data': extracted or {}
            }
            
        except Exception as e:
            print(f"Error in conversational response: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return {
                'response': "Sorry, I'm having issues. Can you try again?",
                'extracted_data': {}
            }
    
    def _get_token_limit(self, conversation_state):
        """Determine appropriate token limit based on context"""
        last_msg = conversation_state.get('last_system_message', '')
        
        if '[Receipt saved successfully]' in last_msg:
            return 300
        elif '[Show confirmation' in last_msg:
            return 300  # Confirmation needs space for summary
        elif '[Receipt processed]' in last_msg:
            return 150
        elif 'processing' in last_msg.lower():
            return 50
        else:
            return 200
    
    def _truncate_by_tokens(self, conversation_history, max_tokens=6000):
        """Truncate conversation history to stay under token limit"""
        if len(conversation_history) <= 3:
            return conversation_history
        
        try:
            count_response = self.client.messages.count_tokens(
                model="claude-sonnet-4-20250514",
                messages=conversation_history
            )
            total_tokens = count_response.input_tokens
        except Exception as e:
            print(f"⚠️  Token counting failed: {e}")
            total_chars = sum(len(str(msg.get('content', ''))) for msg in conversation_history)
            total_tokens = total_chars // 4
        
        print(f"🔢 Total tokens in history: {total_tokens}")
        
        if total_tokens <= max_tokens:
            return conversation_history
        
        first_messages = conversation_history[:2]
        remaining_messages = conversation_history[2:]
        kept_messages = []
        
        try:
            first_count = self.client.messages.count_tokens(
                model="claude-sonnet-4-20250514",
                messages=first_messages
            ).input_tokens
            current_tokens = first_count
        except:
            current_tokens = sum(len(str(msg.get('content', ''))) for msg in first_messages) // 4
        
        for msg in reversed(remaining_messages):
            try:
                msg_tokens = self.client.messages.count_tokens(
                    model="claude-sonnet-4-20250514",
                    messages=[msg]
                ).input_tokens
            except:
                msg_tokens = len(str(msg.get('content', ''))) // 4
            
            if current_tokens + msg_tokens <= max_tokens:
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                break
        
        result = first_messages + kept_messages
        print(f"✂️  Truncated: {len(conversation_history)} → {len(result)} messages")
        
        return result
    
    def _build_system_prompt(self, conversation_state, learned_patterns, extracted_data):
        """Build system prompt with personality, context, and patterns"""
        
        last_msg = conversation_state.get('last_system_message', '')
        suggested_pattern = conversation_state.get('suggested_pattern')
        
        user = conversation_state.get('user', {})
        cost_center_label = user.get('cost_center_label', 'property/unit')
        default_language = user.get('default_language', 'en')
        
        language_names = {
            'es': 'Spanish',
            'en': 'English',
            'pt': 'Portuguese'
        }
        language_name = language_names.get(default_language, 'English')
        
        patterns_text = ""
        if suggested_pattern:
            patterns_text = f"""
PATTERN MATCH FOUND ({suggested_pattern['similarity']:.0f}% similarity):
- Previously used: Category="{suggested_pattern['category_name']}", Cost Center="{suggested_pattern['cost_center_name']}"
- ASK IMMEDIATELY: "Last time you used '{suggested_pattern['category_name']}' for this merchant. Use the same?"
"""
        
        requires_cost_center = user.get('requires_cost_center', True)
        cost_centers = conversation_state.get('cost_centers', [])
        properties_text = ""
        if cost_centers and requires_cost_center:
            properties_text = f"""
AVAILABLE COST CENTERS ({cost_center_label}):
{', '.join(cost_centers)}

IMPORTANT: When user provides a cost center name, use fuzzy matching to find the closest match.
"""
        
        situation_text = self._build_situation_context(conversation_state, last_msg, extracted_data, cost_center_label)
        
        return f"""You are Atina, an AI receipt assistant for property managers.

LANGUAGE: The company's preferred language is {language_name}. Use this by default, but naturally match the user's language if they write in a different one.

PERSONALITY:
- Direct and concise - get to the point fast
- Friendly but efficient - no fluff
- Keep responses under 2 sentences unless providing final summary

{patterns_text}

{properties_text}

CURRENT SITUATION:
{situation_text}

RESPONSE RULES:
1. Match the user's language naturally throughout the conversation
2. Be brief - max 3 sentences per message (except summaries)
3. When asking for category: list 1-2 options in bullet points
4. When asking for cost center: use the term "{cost_center_label}"
5. Accept user's answer immediately - don't confirm unless unclear
6. CRITICAL - ANTI-HALLUCINATION: For receipt details (merchant name, amount), ONLY use values from CURRENT SITUATION above. NEVER use receipt details from conversation history.
7. SKIP HANDLING (rare exception):
   - If user casually says "skip" → DO NOT accept. Re-ask helpfully.
   - Only strong intent like "this doesn't apply", "no category needed" → ask confirmation
   - After user confirms skip → include skip in JSON
8. NEVER claim to edit previously saved receipts. Once saved, it cannot be changed through this chat.
9. When user says data is incorrect, ask "What needs to be fixed?" and let them provide the correct value.

STRUCTURED DATA:
When user provides category or cost center, include JSON:
```json
{{"category": "value or null", "cost_center": "value or null"}}
```

For corrections during fix mode, include the corrected field:
```json
{{"merchant_name": "correct value"}}
```
or
```json
{{"total_amount": 12345}}
```

CRITICAL: JSON is for internal extraction ONLY. Users must NEVER see JSON.
Always include conversational response BEFORE any JSON."""
    
    def _build_situation_context(self, conversation_state, last_msg, extracted_data, cost_center_label='property/unit'):
        """Build concise context based on current state"""
        state_type = conversation_state.get('state', 'new')
        
        if state_type == 'new':
            return "User greeted or no receipt sent. Ask for receipt photo (1 sentence)."
        
        elif '[User just sent a receipt image' in last_msg:
            return "Tell user you're processing the receipt. Keep it brief."
        
        elif '[Tell user you\'re saving' in last_msg:
            return "Tell user you're saving. Keep it brief."
        
        elif '[Bank transfer detected' in last_msg:
            amount = extracted_data.get('total_amount', '0.00')
            return f"Bank transfer detected, ${amount}. Ask: 'Who was this payment to?'"
        
        elif '[Show confirmation summary and ask if correct]' in last_msg:
            # NEW: Confirmation step
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            category = extracted_data.get('category', 'Unknown')
            cost_center = extracted_data.get('cost_center', 'Unknown')
            cc_term = cost_center_label.split('/')[0].capitalize()
            
            return f"""Show this summary and ask for confirmation:

📋 **Receipt Summary:**
• Merchant: {merchant}
• Amount: ${amount}
• Category: {category}
• {cc_term}: {cost_center}

Ask: "Is this correct? (yes/no)"

If user says yes → they will confirm and we save.
If user says no → ask what needs to be fixed."""
        
        elif '[User said data is incorrect' in last_msg:
            # NEW: Fixing mode
            return """User said the data is incorrect. Ask them:
"What needs to be fixed? You can correct the merchant name, amount, category, or property."

When they provide the correct value, extract it in JSON format."""
        
        elif '[Receipt processed, ask for category only]' in last_msg:
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            return f"Receipt: {merchant}, ${amount}. Ask ONLY for category with 2-3 options in bullets."
        
        elif '[Receipt processed, ask for cost_center only]' in last_msg:
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            cc_term = cost_center_label.split('/')[0]
            return f"Receipt: {merchant}, ${amount}. Have category. Ask ONLY for {cc_term}."
        
        elif '[Receipt processed' in last_msg:
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            cc_term = cost_center_label.split('/')[0]
            
            if has_category and has_cost_center:
                return "Have both category and cost center. Acknowledge."
            elif has_category:
                return f"Receipt: {merchant}, ${amount}. Have category. Ask ONLY for {cc_term}."
            elif has_cost_center:
                return f"Receipt: {merchant}, ${amount}. Have {cc_term}. Ask ONLY for category."
            else:
                return f"Receipt: {merchant}, ${amount}. Ask for category with 2-3 options."
        
        elif '[Receipt saved successfully]' in last_msg:
            data = extracted_data
            cc_term = cost_center_label.split('/')[0].capitalize()
            return f"""Provide success summary:

✅ Receipt saved!

• Merchant: {data.get('merchant_name', 'Unknown')}
• Amount: ${data.get('total_amount', '0.00')}
• Category: {data.get('category', 'Unknown')}
• {cc_term}: {data.get('cost_center', 'Unknown')}

Ask: "Do you have another receipt?" """
        
        elif '[User sent a duplicate receipt]' in last_msg:
            return "Duplicate detected. Ask if they want to process anyway."
        
        elif '[Error' in last_msg:
            return "Error occurred. Apologize briefly, ask to try again."
        
        elif '[User confirmed duplicate' in last_msg:
            return "Processing duplicate. Keep it brief."
        
        else:
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            
            if not has_category:
                return "Ask for category with 2-3 options. Be brief."
            elif not has_cost_center:
                return "Ask for property/unit (1 sentence)"
            else:
                return "Have both. Acknowledge."
    
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
        """Remove ALL JSON blocks from response"""
        text = re.sub(r'```json\s*.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'\{[^{}]*\}', '', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        
        cleaned = text.strip()
        
        if not cleaned or not cleaned.strip():
            return "..."
        
        return cleaned


# Global instance
conversational = ConversationalHandler()