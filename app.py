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

# Store conversation states in memory (use Redis/DB in production)
conversation_states = {}

# Store learned patterns per user (use database in production)
user_patterns = {}


def get_user_state(phone_number):
    """Get or create user state with memory"""
    if phone_number not in conversation_states:
        # Load learned patterns if they exist
        patterns = user_patterns.get(phone_number, {})
        
        conversation_states[phone_number] = {
            'state': 'new',
            'conversation_history': [],
            'learned_patterns': patterns,
            'extracted_data': {}
        }
    
    return conversation_states[phone_number]


def save_learned_pattern(phone_number, merchant, category, property_unit):
    """Save learned pattern for future use"""
    if phone_number not in user_patterns:
        user_patterns[phone_number] = {}
    
    merchant_key = merchant.lower().strip()
    user_patterns[phone_number][merchant_key] = {
        'category': category,
        'property': property_unit
    }
    
    # Also update in conversation state
    if phone_number in conversation_states:
        conversation_states[phone_number]['learned_patterns'] = user_patterns[phone_number]
    
    # In production: Save to database here
    print(f"💾 Learned pattern: {merchant} → {category} / {property_unit}")


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
    """Process receipt image from WhatsApp"""
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
        
        # Tell user we're processing
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
        
        # Ask for category (Claude will check learned patterns)
        result = conversational.get_conversational_response(
            user_message=f"[Receipt processed]",
            conversation_state=state
        )
        
        whatsapp.send_message(from_number, result['response'])
        
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


def handle_text_response(from_number, text):
    """Handle text responses from user"""
    
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
        if text.lower() in ['yes', 'y', 'si', 'sí']:
            pending = state.pop('pending_image')
            state.pop('awaiting_duplicate_confirmation')
            
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
            
            result = conversational.get_conversational_response(
                user_message=f"[Receipt processed]",
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
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
        # Get conversational response
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state
        )
        
        # Send response
        whatsapp.send_message(from_number, result['response'])
        
        # Update extracted data if Claude provided values
        if result['extracted_data']:
            for key, value in result['extracted_data'].items():
                if value:
                    state['extracted_data'][key] = value
        
        # Check if we have everything
        has_category = bool(state['extracted_data'].get('category'))
        has_cost_center = bool(state['extracted_data'].get('cost_center'))
        
        # If we have both, save pattern and finalize
        if has_category and has_cost_center:
            # LEARNING LOOP: Save the pattern
            merchant = state['extracted_data'].get('merchant_name', '')
            category = state['extracted_data'].get('category')
            property_unit = state['extracted_data'].get('cost_center')
            
            if merchant and category and property_unit:
                save_learned_pattern(from_number, merchant, category, property_unit)
            
            finalize_receipt(from_number)


def finalize_receipt(from_number):
    """Save receipt to Sheets"""
    state = conversation_states[from_number]
    
    try:
        # Tell user we're saving
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
        
        # Success message
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
            'extracted_data': {}
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