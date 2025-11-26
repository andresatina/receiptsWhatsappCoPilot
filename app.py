from dotenv import load_dotenv
load_dotenv()  # Add this line right after imports

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

def get_message(from_number, msg_key):
    """Get message in user's language"""
    # Check if we know the user's language from previous conversation
    # Default to Spanish for property management users
    lang = conversation_states.get(from_number, {}).get('language', 'es')
    
    messages = {
        'processing': {
            'en': '🔍 Processing your receipt...',
            'es': '🔍 Procesando tu recibo...'
        },
        'saving': {
            'en': '💾 Saving receipt...',
            'es': '💾 Guardando recibo...'
        },
        'saved': {
            'en': '✅ Receipt saved successfully!',
            'es': '✅ Recibo guardado exitosamente!'
        },
        'logged': {
            'en': '📊 Logged in Google Sheets',
            'es': '📊 Registrado en Google Sheets'
        },
        'send_another': {
            'en': 'Send another receipt anytime!',
            'es': '¡Envía otro recibo cuando quieras!'
        }
    }
    
    return messages.get(msg_key, {}).get(lang, messages.get(msg_key, {}).get('en', ''))

def detect_language(text):
    """Simple language detection"""
    text_lower = text.lower()
    spanish_words = ['hola', 'sí', 'si', 'no', 'gracias', 'por favor', 'qué', 'cuál', 'para', 'de', 'la', 'el']
    
    # Count Spanish words
    spanish_count = sum(1 for word in spanish_words if word in text_lower)
    
    return 'es' if spanish_count > 0 else 'en'

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
    
    # Extract message details
    try:
        # Kapso format (different from Meta)
        if 'message' in data:
            message = data['message']
            from_number = message['from']
            message_type = message['type']
            
            # Handle image messages (receipts)
            if message_type == 'image':
                handle_receipt_image(from_number, message)
            
            # Handle text messages (responses to questions)
            elif message_type == 'text':
                handle_text_response(from_number, message['text']['body'])
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def handle_receipt_image(from_number, message):
    """Process receipt image from WhatsApp"""
    try:
        # Kapso provides direct image URL
        image_url = message['kapso']['media_url']
        
        # Download image from URL
        import requests
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        
        # Check for duplicate
        image_hash = hashlib.sha256(image_data).hexdigest()
        if sheets.is_duplicate(image_hash):
            whatsapp.send_message(
                from_number,
                "⚠️ This receipt appears to be a duplicate. Do you want to file it anyway? Reply 'yes' to confirm or 'no' to cancel."
            )
            conversation_states[from_number] = {
                'state': 'duplicate_confirmation',
                'image_data': image_data,
                'image_hash': image_hash
            }
            return
        
        # Extract data using Claude
        # Default to Spanish for first-time image senders (can be updated when they respond)
        if from_number not in conversation_states:
            conversation_states[from_number] = {'language': 'es'}  # Default to Spanish
        
        whatsapp.send_message(from_number, get_message(from_number, 'processing'))
        
        extracted_data = claude.extract_receipt_data(image_data)
        
        # Initialize conversation state
        conversation_states[from_number] = {
            'state': 'collecting_info',
            'image_data': image_data,
            'image_hash': image_hash,
            'extracted_data': extracted_data,
            'missing_fields': []
        }
        
        # Ask for missing information
        ask_for_missing_info(from_number)
        
    except Exception as e:
        print(f"Error handling receipt image: {str(e)}")
        whatsapp.send_message(
            from_number,
            f"❌ Error processing receipt: {str(e)}\n\nPlease try again or send a clearer image."
        )

def handle_text_response(from_number, text):
    """Handle text responses from user with natural conversation"""
    
    # Detect and store language if not already set
    if from_number in conversation_states:
        if 'language' not in conversation_states[from_number]:
            conversation_states[from_number]['language'] = detect_language(text)
    
    if from_number not in conversation_states:
        whatsapp.send_message(
            from_number,
            "👋 Hi! Please send me a receipt image to get started."
        )
        return
    
    state = conversation_states[from_number]
    
    # Handle duplicate confirmation
    if state['state'] == 'duplicate_confirmation':
        if text.lower() in ['yes', 'y', 'si', 'sí']:
            state['state'] = 'collecting_info'
            ask_for_missing_info(from_number)
        else:
            whatsapp.send_message(from_number, "✅ Receipt filing cancelled.")
            del conversation_states[from_number]
        return
    
    # Handle collecting missing info with conversational AI
    if state['state'] == 'collecting_info':
        # Get conversational response from Claude
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state,
            whatsapp_handler=whatsapp
        )
        
        # Send the natural response (Claude already asked the next question if needed)
        whatsapp.send_message(from_number, result['response'])
        
        # Update extracted data if Claude provided values
        if result['extracted_data']:
            for key, value in result['extracted_data'].items():
                if value:  # Only update if there's a real value
                    state['extracted_data'][key] = value
        
        # Check if we have everything we need
        has_category = bool(state['extracted_data'].get('category'))
        has_cost_center = bool(state['extracted_data'].get('cost_center'))
        
        # If we have both, finalize
        if has_category and has_cost_center:
            finalize_receipt(from_number)
        # Otherwise, Claude's response already asked for what's missing

def ask_for_missing_info(from_number):
    """Ask user for missing information"""
    state = conversation_states[from_number]
    extracted_data = state['extracted_data']
    
    # Check what's missing
    required_fields = ['category', 'cost_center']
    missing = [f for f in required_fields if not extracted_data.get(f)]
    
    if missing:
        # Ask for the first missing field
        field = missing[0]
        if field == 'category':
            question = "📂 What category is this expense? (e.g., Maintenance, Utilities, Repairs, Supplies)"
        elif field == 'cost_center':
            question = "🏠 Which property/unit is this expense for?"
        
        state['current_question'] = field
        whatsapp.send_message(from_number, question)
    else:
        # All info collected, finalize
        finalize_receipt(from_number)

def finalize_receipt(from_number):
    """Save receipt to Sheets and Drive"""
    state = conversation_states[from_number]
    
    try:
        whatsapp.send_message(from_number, get_message(from_number, 'saving'))
        
        # Upload to Google Drive - TEMPORARILY DISABLED (permissions issue)
        # image_filename = f"receipt_{state['image_hash'][:8]}.jpg"
        # drive_url = drive.upload_image(state['image_data'], image_filename)
        
        # Add Drive URL to data
        state['extracted_data']['drive_url'] = 'N/A'  # Placeholder until Drive permissions fixed
        state['extracted_data']['image_hash'] = state['image_hash']
        
        # Save to Google Sheets
        sheets.add_receipt(state['extracted_data'])
        
        # Send confirmation
        data = state['extracted_data']
        lang = state.get('language', 'en')
        
        if lang == 'es':
            confirmation = f"""{get_message(from_number, 'saved')}

📝 Resumen:
• Comercio: {data.get('merchant_name', 'N/A')}
• Fecha: {data.get('date', 'N/A')}
• Monto: ${data.get('total_amount', 'N/A')}
• Categoría: {data.get('category', 'N/A')}
• Propiedad: {data.get('cost_center', 'N/A')}
• Pago: {data.get('payment_method', 'N/A')}

{get_message(from_number, 'logged')}

{get_message(from_number, 'send_another')}"""
        else:
            confirmation = f"""{get_message(from_number, 'saved')}

📝 Summary:
• Merchant: {data.get('merchant_name', 'N/A')}
• Date: {data.get('date', 'N/A')}
• Amount: ${data.get('total_amount', 'N/A')}
• Category: {data.get('category', 'N/A')}
• Property: {data.get('cost_center', 'N/A')}
• Payment: {data.get('payment_method', 'N/A')}

{get_message(from_number, 'logged')}

{get_message(from_number, 'send_another')}"""
        
        whatsapp.send_message(from_number, confirmation)
        
        # Clear conversation state
        del conversation_states[from_number]
        
    except Exception as e:
        print(f"Error finalizing receipt: {str(e)}")
        whatsapp.send_message(
            from_number,
            f"❌ Error saving receipt: {str(e)}\n\nPlease contact support."
        )

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)