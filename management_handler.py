"""
Management Handler for /manage command
Allows users to add, delete, and list cost centers and categories
"""

import os
import anthropic
import json


class ManagementHandler:
    """Handles management commands for cost centers and categories"""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    
    def handle_management(self, user_message, state, db):
        """
        Process management commands using Claude for natural language understanding
        
        Returns: (response_message, should_exit_management_mode)
        """
        company_id = state['company_id']
        user = state['user']
        cost_center_label = user.get('cost_center_label', 'property/unit')
        term = cost_center_label.split('/')[0]  # "property", "job", etc.
        
        # Get current lists
        categories = [c['name'] for c in db.get_categories(company_id)]
        cost_centers = [cc['name'] for cc in db.get_cost_centers(company_id)]
        
        # Check if awaiting confirmation
        pending = state.get('pending_management_action')
        if pending:
            # User is responding to confirmation
            if user_message.lower() in ['yes', 'y', 'si', 'sí', 'ok', 'confirm']:
                return self._execute_pending_action(pending, state, db, term)
            else:
                state.pop('pending_management_action', None)
                return (f"Cancelled. What else would you like to do?", False)
        
        # Use Claude to understand the request
        system_prompt = f"""You are helping manage {term}s and categories for a business.

CURRENT DATA:
- Categories: {', '.join(categories) if categories else 'None'}
- {term.capitalize()}s: {', '.join(cost_centers) if cost_centers else 'None'}

Parse the user's request and respond with JSON only:
{{
    "action": "add" | "delete" | "list" | "exit" | "unclear",
    "type": "cost_center" | "category" | "both" | null,
    "name": "the name to add/delete" | null,
    "message": "friendly response to show user"
}}

RULES:
- For "list" requests, set type to what they want to list (or "both" if not specific)
- For "done", "exit", "finished", "salir" → action: "exit"
- Use "{term}" terminology (not "cost center") in your message
- Keep messages brief and friendly
- Match the user's language (Spanish/English)"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            result = self._parse_json(response.content[0].text)
            
            if not result:
                return (f"I didn't understand that. You can add, delete, or list {term}s and categories. Or say 'done' to exit.", False)
            
            action = result.get('action')
            item_type = result.get('type')
            name = result.get('name')
            message = result.get('message', '')
            
            # Handle actions
            if action == 'exit':
                state['state'] = 'new'
                return ("✅ Management mode closed. Send a receipt when you're ready!", True)
            
            elif action == 'list':
                return self._handle_list(item_type, categories, cost_centers, term)
            
            elif action == 'add' and name:
                # Store pending action and ask for confirmation
                state['pending_management_action'] = {
                    'action': 'add',
                    'type': item_type,
                    'name': name
                }
                type_label = term if item_type == 'cost_center' else 'category'
                return (f"Add {type_label} '{name}'? (yes/no)", False)
            
            elif action == 'delete' and name:
                # Store pending action and ask for confirmation
                state['pending_management_action'] = {
                    'action': 'delete',
                    'type': item_type,
                    'name': name
                }
                type_label = term if item_type == 'cost_center' else 'category'
                return (f"Delete {type_label} '{name}'? (yes/no)", False)
            
            else:
                return (message or f"What would you like to do? You can add, delete, or list {term}s and categories.", False)
                
        except Exception as e:
            print(f"Management handler error: {e}")
            return (f"Sorry, something went wrong. Try again or say 'done' to exit.", False)
    
    def _handle_list(self, item_type, categories, cost_centers, term):
        """Handle list requests"""
        if item_type == 'category':
            if categories:
                return (f"📋 Categories:\n• " + "\n• ".join(categories), False)
            return ("No categories found.", False)
        
        elif item_type == 'cost_center':
            if cost_centers:
                return (f"📋 {term.capitalize()}s:\n• " + "\n• ".join(cost_centers), False)
            return (f"No {term}s found.", False)
        
        else:  # both
            response = ""
            if categories:
                response += f"📋 Categories:\n• " + "\n• ".join(categories)
            else:
                response += "No categories found."
            
            response += "\n\n"
            
            if cost_centers:
                response += f"📋 {term.capitalize()}s:\n• " + "\n• ".join(cost_centers)
            else:
                response += f"No {term}s found."
            
            return (response, False)
    
    def _execute_pending_action(self, pending, state, db, term):
        """Execute a confirmed action"""
        action = pending['action']
        item_type = pending['type']
        name = pending['name']
        company_id = state['company_id']
        
        state.pop('pending_management_action', None)
        
        type_label = term if item_type == 'cost_center' else 'category'
        
        if action == 'add':
            if item_type == 'cost_center':
                db.add_cost_center(company_id, name)
            else:
                db.add_category(company_id, name)
            return (f"✅ {type_label.capitalize()} '{name}' added! What else?", False)
        
        elif action == 'delete':
            if item_type == 'cost_center':
                success = db.delete_cost_center(company_id, name)
            else:
                success = db.delete_category(company_id, name)
            
            if success:
                return (f"✅ {type_label.capitalize()} '{name}' deleted! What else?", False)
            else:
                return (f"❌ {type_label.capitalize()} '{name}' not found. What else?", False)
        
        return ("Something went wrong. What else would you like to do?", False)
    
    def _parse_json(self, text):
        """Extract JSON from response"""
        try:
            # Clean up response
            text = text.strip()
            if '```json' in text:
                start = text.find('```json') + 7
                end = text.find('```', start)
                text = text[start:end].strip()
            elif '```' in text:
                start = text.find('```') + 3
                end = text.find('```', start)
                text = text[start:end].strip()
            
            return json.loads(text)
        except:
            return None


# Global instance
management_handler = ManagementHandler()
