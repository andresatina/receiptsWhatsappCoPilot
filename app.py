from dotenv import load_dotenv
load_dotenv()

import os
from flask import Flask, request, jsonify
import hashlib
import json

from whatsapp_handler import WhatsAppHandler
from claude_handler import ClaudeHandler
from sheets_handler import SheetsHandler
from drive_handler import DriveHandler
from conversational_helper import conversational
from database_handler import DatabaseHandler

app = Flask(__name__)

# Initialize handlers
whatsapp = WhatsAppHandler(
    api_key=os.getenv('KAPSO_API_KEY'),
    phone_number=os.getenv('WHATSAPP_PHONE_NUMBER')
)
claude = ClaudeHandler(api_key=os.getenv('CLAUDE_API_KEY'))
sheets = SheetsHandler(
    credentials_path='credentials.json',
    sheet_id=os.getenv('GOOGLE_SHEET_ID')
)
drive = DriveHandler(
    credentials_path='credentials.json',
    folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_ID')
)
db = DatabaseHandler()  # PostgreSQL handler

# Store conversation states in memory (temporary, per session only)
# Learned patterns now stored in PostgreSQL
conversation_states = {}


def get_user_state(phone_number):
    """Get or create user state - loads from database"""
    if phone_number not in conversation_states:
        # Ensure client exists in database
        db.get_or_create_client(phone_number)
        
        # Load categories and cost centers from database
        categories = db.get_categories(phone_number)
        cost_centers = db.get_cost_centers(phone_number)
        
        conversation_states[phone_number] = {
            'state': 'new',
            'conversation_history': [],
            'categories': [c['name'] for c in categories],  # Available categories
            'cost_centers': [cc['name'] for cc in cost_centers],  # Available cost centers
            'extracted_data': {},
            'asked_for_category': False,
            'asked_for_property': False
        }
    
    return conversation_states[phone_number]


def save_learned_pattern(phone_number, merchant, items_text, category, cost_center):
    """Save learned pattern to database with item keywords"""
    
    # Debug: Log what we received
    print(f"🔍 save_learned_pattern called:")
    print(f"   merchant: {merchant}")
    print(f"   items_text: '{items_text}'")
    print(f"   category: {category}")
    print(f"   cost_center: {cost_center}")
    
    # Extract keywords from items (simple approach - split and filter)
    items_keywords = []
    if items_text:
        # Split by common separators, lowercase, remove numbers/prices
        import re
        words = re.split(r'[\n,\$\d\.\s]+', items_text.lower())
        # Keep words longer than 2 chars
        items_keywords = [w.strip() for w in words if len(w.strip()) > 2]
        # Remove duplicates, keep unique
        items_keywords = list(set(items_keywords))[:10]  # Max 10 keywords
    
    print(f"   📝 Extracted keywords: {items_keywords}")
    
    # Save to database
    db.save_pattern(
        client_id=phone_number,
        merchant=merchant,
        items_keywords=items_keywords,
        category_name=category,
        cost_center_name=cost_center
    )




@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """Handle Kapso webhook for incoming WhatsApp messages"""
    
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if verify_token == os.getenv('WEBHOOK_VERIFY_TOKEN'):
            return challenge
        return 'Invalid verify token', 403
    
    data = request.json
    print(f"Received webhook: {json.dumps(data, indent=2)}")
    
    try:
        if 'message' not in data:
            return jsonify({'status': 'ok', 'note': 'no message in webhook'})
        
        message = data['message']
        from_number = message['from']
        message_type = message['type']
        
        if message_type == 'image':
            handle_receipt_image(from_number, message)
        elif message_type == 'text':
            handle_text_response(from_number, message['text']['body'])
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


def handle_receipt_image(from_number, message):
    """Process receipt image from WhatsApp - OPTIMIZED FLOW"""
    try:
        state = get_user_state(from_number)
        
        # Download image
        image_url = message['kapso']['media_url']
        import requests
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        
        # Check for duplicate
        image_hash = hashlib.sha256(image_data).hexdigest()
        if sheets.is_duplicate(image_hash):
            result = conversational.get_conversational_response(
                user_message="[User sent a duplicate receipt]",
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
            state['awaiting_duplicate_confirmation'] = True
            state['pending_image'] = {'data': image_data, 'hash': image_hash}
            return
        
        # IMPROVEMENT #3: Single "Processing..." message (not multiple)
        state['last_system_message'] = "[User just sent a receipt image, tell them you're processing it]"
        result = conversational.get_conversational_response(
            user_message="[User just sent a receipt image, tell them you're processing it]",
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])
        
        # Extract data
        extracted_data = claude.extract_receipt_data(image_data)
        
        # Store in state
        state['state'] = 'collecting_info'
        state['image_data'] = image_data
        state['image_hash'] = image_hash
        state['extracted_data'] = extracted_data
        state['last_system_message'] = "[Receipt processed]"
        state['asked_for_category'] = False
        state['asked_for_property'] = False
        
        # IMPROVEMENT #1: Ask for missing info ONCE (check what we need)
        ask_for_missing_info(from_number, state)
        
    except Exception as e:
        print(f"Error handling receipt image: {str(e)}")
        import traceback
        traceback.print_exc()
        state = get_user_state(from_number)
        result = conversational.get_conversational_response(
            user_message="[Error processing receipt image]",
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])


def ask_for_missing_info(from_number, state):
    """
    Check database for patterns, suggest if found, otherwise ask
    """
    has_category = bool(state['extracted_data'].get('category'))
    has_property = bool(state['extracted_data'].get('cost_center'))
    
    # If we have both, finalize immediately
    if has_category and has_property:
        finalize_receipt(from_number)
        return
    
    # Check for matching patterns in database
    merchant = state['extracted_data'].get('merchant_name', '')
    items_text = state['extracted_data'].get('items', '')
    
    if merchant:
        # Extract keywords from current receipt items (if available)
        items_keywords = []
        if items_text:
            import re
            words = re.split(r'[\n,\$\d\.\s]+', items_text.lower())
            items_keywords = [w.strip() for w in words if len(w.strip()) > 2]
            items_keywords = list(set(items_keywords))[:10]
        
        # Find matching patterns (works even with empty items_keywords)
        matches = db.find_matching_patterns(from_number, merchant, items_keywords)
        
        if matches and matches[0]['similarity'] >= 60:
            # Good match found - add to state for conversational AI to use
            best_match = matches[0]
            state['suggested_pattern'] = {
                'category': best_match['category_name'],
                'cost_center': best_match['cost_center_name'],
                'similarity': best_match['similarity']
            }
    
    # Let conversational AI ask (will use suggested_pattern if available)
    result = conversational.get_conversational_response(
        user_message="[Receipt processed, ask for what's missing]",
        conversation_state=state
    )
    whatsapp.send_message(from_number, result['response'])
    
    # Track what we've asked for
    if not has_category:
        state['asked_for_category'] = True
    if not has_property:
        state['asked_for_property'] = True


def handle_text_response(from_number, text):
    """Handle text responses from user - OPTIMIZED"""
    
    state = get_user_state(from_number)
    
    # If user is new (no receipt sent yet)
    if state.get('state') == 'new':
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])
        return
    
    # Handle duplicate confirmation
    if state.get('awaiting_duplicate_confirmation'):
        if text.lower() in ['yes', 'y', 'si', 'sí', 'si']:
            pending = state.pop('pending_image')
            state.pop('awaiting_duplicate_confirmation')
            
            # Brief processing message
            state['last_system_message'] = "[User confirmed duplicate, tell them you're processing it now]"
            result = conversational.get_conversational_response(
                user_message="[User confirmed duplicate, tell them you're processing it now]",
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
            
            extracted_data = claude.extract_receipt_data(pending['data'])
            state['state'] = 'collecting_info'
            state['image_data'] = pending['data']
            state['image_hash'] = pending['hash']
            state['extracted_data'] = extracted_data
            state['last_system_message'] = "[Receipt processed]"
            state['asked_for_category'] = False
            state['asked_for_property'] = False
            
            ask_for_missing_info(from_number, state)
        else:
            state.pop('pending_image', None)
            state.pop('awaiting_duplicate_confirmation', None)
            result = conversational.get_conversational_response(
                user_message="[User cancelled duplicate receipt]",
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
        return
    
    # Handle collecting info
    if state.get('state') == 'collecting_info':
        # IMPROVEMENT #4: Get conversational response and extract data
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state
        )
        
        # Update extracted data if Claude provided values
        if result['extracted_data']:
            for key, value in result['extracted_data'].items():
                if value:
                    state['extracted_data'][key] = value
        
        # Check what we have now
        has_category = bool(state['extracted_data'].get('category'))
        has_property = bool(state['extracted_data'].get('cost_center'))
        
        # IMPROVEMENT #4: No confirmation loop - just proceed
        if has_category and has_property:
            # We have everything - save and finalize
            merchant = state['extracted_data'].get('merchant_name', '')
            items = state['extracted_data'].get('items', '')  # Get items text
            category = state['extracted_data'].get('category')
            property_unit = state['extracted_data'].get('cost_center')
            
            if merchant and category and property_unit:
                save_learned_pattern(from_number, merchant, items, category, property_unit)
            
            finalize_receipt(from_number)
        else:
            # IMPROVEMENT #1: Ask for what's still missing (only once)
            # Send the response we got (might be asking for clarification)
            whatsapp.send_message(from_number, result['response'])
            
            # If Claude didn't ask for the next thing, we ask
            if has_category and not has_property and not state.get('asked_for_property'):
                state['asked_for_property'] = True
                # Claude should have asked in the response above, so we don't double-ask


def finalize_receipt(from_number):
    """Save receipt to Sheets - OPTIMIZED"""
    state = conversation_states[from_number]
    
    try:
        # IMPROVEMENT #3: Single short "Saving..." message
        state['last_system_message'] = "[Tell user you're saving the receipt now]"
        result = conversational.get_conversational_response(
            user_message="[Tell user you're saving the receipt now]",
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])
        
        # Save to Sheets
        state['extracted_data']['drive_url'] = 'N/A'
        state['extracted_data']['image_hash'] = state['image_hash']
        sheets.add_receipt(state['extracted_data'])
        
        # IMPROVEMENT #2: Concise success message with summary
        state['last_system_message'] = "[Receipt saved successfully]"
        result = conversational.get_conversational_response(
            user_message="[Receipt saved successfully]",
            conversation_state=state
        )
        
        whatsapp.send_message(from_number, result['response'])
        
        # Clear state but keep learned patterns and conversation history
        learned_patterns = state.get('learned_patterns', {})
        conversation_history = state.get('conversation_history', [])
        
        conversation_states[from_number] = {
            'state': 'new',
            'conversation_history': conversation_history,
            'learned_patterns': learned_patterns,
            'extracted_data': {},
            'asked_for_category': False,
            'asked_for_property': False
        }
        
    except Exception as e:
        print(f"Error finalizing receipt: {str(e)}")
        import traceback
        traceback.print_exc()
        
        result = conversational.get_conversational_response(
            user_message="[Error saving receipt]",
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)