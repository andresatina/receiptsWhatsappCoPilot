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
        
        # CRITICAL: Filter out messages with empty content (Claude API requirement)
        # Empty messages cause: "messages.X: all messages must have non-empty content"
        conversation_history = [
            msg for msg in conversation_history 
            if msg.get('content', '').strip()
        ]
        
        # Token-based truncation (max ~6000 tokens for history, leaving room for system prompt)
        conversation_history = self._truncate_by_tokens(conversation_history, max_tokens=6000)
        
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
            print(f"Messages count: {len(conversation_history) if 'conversation_history' in locals() else 'N/A'}")
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
    
    def _truncate_by_tokens(self, conversation_history, max_tokens=6000):
        """
        Truncate conversation history to stay under token limit
        Strategy: Keep first 2 messages (greeting) + last N messages (recent context)
        """
        if len(conversation_history) <= 3:
            return conversation_history  # Too short to truncate
        
        # Use Anthropic's token counter - need model to count
        try:
            count_response = self.client.messages.count_tokens(
                model="claude-sonnet-4-20250514",
                messages=conversation_history
            )
            total_tokens = count_response.input_tokens
        except Exception as e:
            print(f"⚠️  Token counting failed: {e}")
            # Fallback: estimate ~4 chars per token
            total_chars = sum(len(str(msg.get('content', ''))) for msg in conversation_history)
            total_tokens = total_chars // 4
        
        print(f"🔢 Total tokens in history: {total_tokens}")
        
        if total_tokens <= max_tokens:
            return conversation_history  # Under limit, keep everything
        
        # Strategy: Keep first 2 + progressively add from end until we hit limit
        first_messages = conversation_history[:2]  # Keep greeting
        remaining_messages = conversation_history[2:]
        
        # Start from most recent and work backwards
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
            # Estimate tokens for this message
            try:
                msg_tokens = self.client.messages.count_tokens(
                    model="claude-sonnet-4-20250514",
                    messages=[msg]
                ).input_tokens
            except:
                msg_tokens = len(str(msg.get('content', ''))) // 4
            
            if current_tokens + msg_tokens <= max_tokens:
                kept_messages.insert(0, msg)  # Add to front (we're going backwards)
                current_tokens += msg_tokens
            else:
                break  # Would exceed limit, stop here
        
        result = first_messages + kept_messages
        
        try:
            final_tokens = self.client.messages.count_tokens(
                model="claude-sonnet-4-20250514",
                messages=result
            ).input_tokens
        except:
            final_tokens = sum(len(str(msg.get('content', ''))) for msg in result) // 4
        
        print(f"✂️  Truncated: {len(conversation_history)} → {len(result)} messages ({total_tokens} → {final_tokens} tokens)")
        
        return result
    
    def _build_system_prompt(self, conversation_state, learned_patterns, extracted_data):
        """Build system prompt with personality, context, and patterns"""
        
        # Get current state
        state_type = conversation_state.get('state', 'new')
        last_msg = conversation_state.get('last_system_message', '')
        suggested_pattern = conversation_state.get('suggested_pattern')
        
        # Get company-specific cost center label
        user = conversation_state.get('user', {})
        cost_center_label = user.get('cost_center_label', 'property/unit')
        
        # Build pattern suggestion context
        patterns_text = ""
        if suggested_pattern:
            patterns_text = f"""
PATTERN MATCH FOUND ({suggested_pattern['similarity']:.0f}% similarity):
- Previously used: Category="{suggested_pattern['category']}", Cost Center="{suggested_pattern['cost_center']}"
- ASK IMMEDIATELY: "Last time you used '{suggested_pattern['category']}' for this merchant. Use the same?"
- DO NOT list category options - just ask for confirmation
- If user says yes/same/correct, extract the suggested category immediately
- Only if user says no, then ask what category they want instead
"""
        
        # Build available properties context (only if company requires cost centers)
        requires_cost_center = user.get('requires_cost_center', True)
        cost_centers = conversation_state.get('cost_centers', [])
        properties_text = ""
        if cost_centers and requires_cost_center:
            properties_text = f"""
AVAILABLE COST CENTERS ({cost_center_label}):
{', '.join(cost_centers)}

IMPORTANT: When user provides a cost center name, use fuzzy matching to find the closest match.
- If user says a shortened version, ask: "Did you mean '[full name]'?"
- Always suggest the closest match from the available list
- Extract the EXACT cost center name from the list (not what user typed)
- When asking for cost center, use the term: "{cost_center_label}"
"""
        
        # Build situation context
        situation_text = self._build_situation_context(conversation_state, last_msg, extracted_data, cost_center_label)
        
        return f"""You are Atina, an AI receipt assistant for property managers.

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
2. Be brief - max 3 sentences per message (except final summary)
3. When asking for category: list 1-2 options in bullet points
4. When asking for cost center: use the term "{cost_center_label}" (NOT "property/unit" unless that's the label)
5. Accept user's answer immediately - don't confirm unless unclear
6. SKIP HANDLING (rare exception):
   - If user casually says "skip", "saltar", "pular" → DO NOT accept. Re-ask the question helpfully.
   - Only if user gives STRONG intent like "this doesn't apply", "no category needed", "es personal", "não se aplica" → ask for confirmation
   - Confirmation must be explicit: "Just to confirm - save this without a [category/property]? (yes/no)"
   - Only after user confirms (yes/si/sim) → include skip in JSON


STRUCTURED DATA:
When user provides category or cost center, include JSON for data extraction:
```json
{{"category": "value or null", "cost_center": "value or null"}}
```

ONLY after user CONFIRMS they want to skip (answered yes to confirmation), respond with:
```json
{{"skip_category": true}}
```
or
```json
{{"skip_cost_center": true}}
```

CRITICAL: The JSON is for internal data extraction ONLY. Users must NEVER see the JSON.
Always include your conversational response BEFORE any JSON.
Example: "Which {cost_center_label.split('/')[0]} is this for?" (user sees this)
{{JSON here}} (system extracts this, user never sees it)

Note: Use "cost_center" in JSON (internal field) but say "{cost_center_label}" to users."""
    
    def _build_situation_context(self, conversation_state, last_msg, extracted_data, cost_center_label='property/unit'):
        """Build concise context based on current state"""
        state_type = conversation_state.get('state', 'new')
        
        if state_type == 'new':
            return "User greeted or no receipt sent. Ask for receipt photo (1 sentence)."
        
        elif '[User just sent a receipt image' in last_msg:
            return "Tell user you're processing the receipt. Keep it brief - just one or two words in their language."
        
        elif '[Tell user you\'re saving' in last_msg:
            return "Tell user you're saving the receipt. Keep it brief - just one or two words in their language."
        
        elif '[Bank transfer detected' in last_msg:
            amount = extracted_data.get('total_amount', '0.00')
            return f"Bank transfer detected, ${amount}. Ask user: 'Who was this payment to?' or 'What was this payment for?' - Get the beneficiary/purpose from them."
        
        elif '[Receipt processed, ask for category only]' in last_msg:
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            return f"Receipt: {merchant}, ${amount}. Ask ONLY for category with 3-5 merchant-appropriate options in bullets. If learned pattern exists, suggest it first. DO NOT ask about cost center yet - one question at a time."
        
        elif '[Receipt processed, ask for cost_center only]' in last_msg:
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            cc_term = cost_center_label.split('/')[0]
            return f"Receipt: {merchant}, ${amount}. Have category already. Ask ONLY for {cc_term}. DO NOT ask about category - we already have it."
        
        elif '[Receipt processed' in last_msg:
            merchant = extracted_data.get('merchant_name', 'Unknown')
            amount = extracted_data.get('total_amount', '0.00')
            has_category = bool(extracted_data.get('category'))
            has_cost_center = bool(extracted_data.get('cost_center'))
            
            # Get the first term from cost_center_label (e.g., "job" from "job/project")
            cc_term = cost_center_label.split('/')[0]
            
            if has_category and has_cost_center:
                return "Already have both category and cost center. This shouldn't happen - just acknowledge."
            elif has_category:
                return f"Receipt: {merchant}, ${amount}. Have category already. Ask ONLY for {cc_term} (nothing else)"
            elif has_cost_center:
                return f"Receipt: {merchant}, ${amount}. Have {cc_term} already. Ask ONLY for category with 3-5 options in bullets"
            else:
                return f"Receipt: {merchant}, ${amount}. Ask for category with 3-5 merchant-appropriate options in bullets. If learned pattern exists, suggest it first."
        
        elif '[Receipt saved successfully]' in last_msg:
            data = extracted_data
            cc_term = cost_center_label.split('/')[0].capitalize()
            return f"""IMPORTANT: You MUST provide a complete summary in this exact format:

✅ Receipt saved successfully!

Details:
• Merchant: {data.get('merchant_name', 'Unknown')}
• Amount: ${data.get('total_amount', '0.00')}
• Category: {data.get('category', 'Unknown')}
• {cc_term}: {data.get('cost_center', 'Unknown')}

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
                return "Ask for category with 3-5 options in bullets. Be brief."
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
        # Remove ```json blocks - handle both with and without newlines
        text = re.sub(r'```json\s*.*?```', '', text, flags=re.DOTALL)
        
        # Remove standalone {...} objects anywhere in text
        text = re.sub(r'\{[^{}]*\}', '', text)
        
        # Clean up extra whitespace and newlines left behind
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        
        cleaned = text.strip()
        
        # CRITICAL: Never return empty string (causes Claude API errors)
        if not cleaned or not cleaned.strip():
            return "..."
        
        return cleaned


# Global instance
conversational = ConversationalHandler()