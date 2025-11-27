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


def detect_language(text):
    """Simple language detection - Spanish or English"""
    text_lower = text.lower()
    spanish_words = ['hola', 'sí', 'si', 'no', 'gracias', 'por favor', 'qué', 'cuál', 'para', 'de', 'la', 'el', 'un', 'una']
    
    spanish_count = sum(1 for word in spanish_words if word in text_lower)
    return 'es' if spanish_count > 0 else 'en'


def get_loading_message(msg_type, language='es'):
    """Get loading messages in user's language"""
    messages = {
        'processing': {
            'es': '🔍 Procesando tu recibo...',
            'en': '🔍 Processing your receipt...'
        },
        'saving': {
            'es': '💾 Guardando recibo...',
            'en': '💾 Saving receipt...'
        }
    }
    return messages.get(msg_type, {}).get(language, messages.get(msg_type, {}).get('es', ''))


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """Handle Kapso webhook for incoming WhatsApp messages"""
    
    if request.method == 'GET':
        # Webhook verification
        verify_token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if verify_token == os.getenv('WEBHOOK_VERIFY_TOKEN'):
            return challenge
        return 'Invalid verify token', 403
    
    # Handle incoming message
    data = request.json
    print(f"Received webhook: {json.dumps(data, indent=2)}")
    
    try:
        if 'message' not in data:
            return jsonify({'status': 'ok', 'note': 'no message in webhook'})
        
        message = data['message']
        from_number = message['from']
        message_type = message['type']
        
        # Handle image messages (receipts)
        if message_type == 'image':
            handle_receipt_image(from_number, message)
        
        # Handle text messages
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
        # Get or create conversation state
        if from_number not in conversation_states:
            conversation_states[from_number] = {
                'language': 'es',  # Default to Spanish
                'state': 'new'
            }
        
        state = conversation_states[from_number]
        lang = state.get('language', 'es')
        
        # Download image
        image_url = message['kapso']['media_url']
        import requests
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        
        # Check for duplicate
        image_hash = hashlib.sha256(image_data).hexdigest()
        if sheets.is_duplicate(image_hash):
            # Let Claude handle duplicate message naturally
            result = conversational.get_conversational_response(
                user_message="[User sent a duplicate receipt]",
                conversation_state=state,
                whatsapp_handler=whatsapp
            )
            whatsapp.send_message(from_number, result['response'])
            state['awaiting_duplicate_confirmation'] = True
            state['pending_image'] = {'data': image_data, 'hash': image_hash}
            return
        
        # Send loading message IMMEDIATELY
        whatsapp.send_message(from_number, get_loading_message('processing', lang))
        
        # Extract data using Claude (slow operation)
        extracted_data = claude.extract_receipt_data(image_data)
        
        # Store in state
        state['state'] = 'collecting_info'
        state['image_data'] = image_data
        state['image_hash'] = image_hash
        state['extracted_data'] = extracted_data
        
        # Get conversational response from Claude
        result = conversational.get_conversational_response(
            user_message=f"[Receipt processed: {extracted_data.get('merchant_name')} for ${extracted_data.get('total_amount')}]",
            conversation_state=state,
            whatsapp_handler=whatsapp
        )
        
        state['last_system_message'] = f"[Receipt processed: {extracted_data.get('merchant_name')} for ${extracted_data.get('total_amount')}]"
        whatsapp.send_message(from_number, result['response'])
        
    except Exception as e:
        print(f"Error handling receipt image: {str(e)}")
        import traceback
        traceback.print_exc()
        # Let Claude handle error naturally
        result = conversational.get_conversational_response(
            user_message="[Error processing receipt image]",
            conversation_state=conversation_states.get(from_number, {'language': 'es'}),
            whatsapp_handler=whatsapp
        )
        whatsapp.send_message(from_number, result['response'])


def handle_text_response(from_number, text):
    """Handle text responses from user"""
    
    # Get or create conversation state
    if from_number not in conversation_states:
        conversation_states[from_number] = {
            'language': detect_language(text),
            'state': 'new'
        }
    
    state = conversation_states[from_number]
    
    # Update language if not set
    if 'language' not in state or state['language'] is None:
        state['language'] = detect_language(text)
    
    # If user is new (no receipt sent yet), let Claude handle greeting
    if state.get('state') == 'new':
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state,
            whatsapp_handler=whatsapp
        )
        whatsapp.send_message(from_number, result['response'])
        return
    
    # Handle duplicate confirmation
    if state.get('awaiting_duplicate_confirmation'):
        if text.lower() in ['yes', 'y', 'si', 'sí']:
            # Process the pending receipt
            pending = state.pop('pending_image')
            state.pop('awaiting_duplicate_confirmation')
            
            lang = state.get('language', 'es')
            whatsapp.send_message(from_number, get_loading_message('processing', lang))
            
            extracted_data = claude.extract_receipt_data(pending['data'])
            state['state'] = 'collecting_info'
            state['image_data'] = pending['data']
            state['image_hash'] = pending['hash']
            state['extracted_data'] = extracted_data
            
            result = conversational.get_conversational_response(
                user_message=f"[User confirmed duplicate, processing receipt]",
                conversation_state=state,
                whatsapp_handler=whatsapp
            )
            whatsapp.send_message(from_number, result['response'])
        else:
            # Cancelled
            state.pop('pending_image', None)
            state.pop('awaiting_duplicate_confirmation', None)
            result = conversational.get_conversational_response(
                user_message="[User cancelled duplicate receipt]",
                conversation_state=state,
                whatsapp_handler=whatsapp
            )
            whatsapp.send_message(from_number, result['response'])
        return
    
    # Handle collecting info with conversational AI
    if state.get('state') == 'collecting_info':
        # Get conversational response from Claude
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state,
            whatsapp_handler=whatsapp
        )
        
        # Send the natural response
        whatsapp.send_message(from_number, result['response'])
        
        # Update extracted data if Claude provided values
        if result['extracted_data']:
            for key, value in result['extracted_data'].items():
                if value:
                    state['extracted_data'][key] = value
        
        # Check if we have everything we need
        has_category = bool(state['extracted_data'].get('category'))
        has_cost_center = bool(state['extracted_data'].get('cost_center'))
        
        # If we have both, finalize
        if has_category and has_cost_center:
            finalize_receipt(from_number)


def finalize_receipt(from_number):
    """Save receipt to Sheets"""
    state = conversation_states[from_number]
    lang = state.get('language', 'es')
    
    try:
        # Send loading message IMMEDIATELY
        whatsapp.send_message(from_number, get_loading_message('saving', lang))
        
        # Save to Google Sheets (slow operation)
        state['extracted_data']['drive_url'] = 'N/A'
        state['extracted_data']['image_hash'] = state['image_hash']
        sheets.add_receipt(state['extracted_data'])
        
        # Let Claude generate the success message and summary
        state['last_system_message'] = "[Receipt saved successfully]"
        result = conversational.get_conversational_response(
            user_message="[Receipt saved successfully]",
            conversation_state=state,
            whatsapp_handler=whatsapp
        )
        
        whatsapp.send_message(from_number, result['response'])
        
        # Clear conversation state
        del conversation_states[from_number]
        
    except Exception as e:
        print(f"Error finalizing receipt: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Let Claude handle error
        result = conversational.get_conversational_response(
            user_message="[Error saving receipt]",
            conversation_state=state,
            whatsapp_handler=whatsapp
        )
        whatsapp.send_message(from_number, result['response'])


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)