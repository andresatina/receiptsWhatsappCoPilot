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
            'extracted_data': {},
            'asked_for_category': False,  # Track what we've asked for
            'asked_for_property': False
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


def _detect_user_language(state):
    """Detect user's preferred language from conversation history"""
    conversation_history = state.get('conversation_history', [])
    
    # Check last few user messages for language hints
    spanish_indicators = ['hola', 'gracias', 'sí', 'si', 'qué', 'bueno', 'apartamento', 'propiedad']
    english_indicators = ['hello', 'hi', 'thanks', 'thank you', 'what', 'good', 'apartment', 'property']
    
    spanish_count = 0
    english_count = 0
    
    for msg in conversation_history[-5:]:  # Check last 5 messages
        if msg.get('role') == 'user':
            content = msg.get('content', '').lower()
            for word in spanish_indicators:
                if word in content:
                    spanish_count += 1
            for word in english_indicators:
                if word in content:
                    english_count += 1
    
    # Default to Spanish if unclear (since you're in Colombia)
    if spanish_count > english_count:
        return "Spanish"
    elif english_count > spanish_count:
        return "English"
    else:
        return "Spanish"  # Default to Spanish


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
        
        # IMPROVEMENT #3: Single "Procesando..." message (not multiple)
        # Detect user's language from conversation history
        user_language = _detect_user_language(state)
        
        state['last_system_message'] = f"[User just sent a receipt image, tell them you're processing it in {user_language}]"
        result = conversational.get_conversational_response(
            user_message=f"[User just sent a receipt image, tell them you're processing it in {user_language}]",
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
    Ask for missing information ONCE - let conversational AI handle it naturally
    """
    has_category = bool(state['extracted_data'].get('category'))
    has_property = bool(state['extracted_data'].get('cost_center'))
    
    # If we have both, finalize immediately
    if has_category and has_property:
        finalize_receipt(from_number)
        return
    
    # Let conversational AI ask the questions with full context
    # It will see what's missing and ask intelligently
    result = conversational.get_conversational_response(
        user_message="[Receipt processed, ask for what's missing]",
        conversation_state=state
    )
    whatsapp.send_message(from_number, result['response'])
    
    # Track what we've asked for (prevent re-asking)
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
            category = state['extracted_data'].get('category')
            property_unit = state['extracted_data'].get('cost_center')
            
            if merchant and category and property_unit:
                save_learned_pattern(from_number, merchant, category, property_unit)
            
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
        # IMPROVEMENT #3: Single short "Guardando..." message in user's language
        user_language = _detect_user_language(state)
        
        state['last_system_message'] = f"[Tell user you're saving the receipt now in {user_language}]"
        result = conversational.get_conversational_response(
            user_message=f"[Tell user you're saving the receipt now in {user_language}]",
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