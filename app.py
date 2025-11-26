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
        whatsapp.send_message(from_number, "🔍 Processing your receipt...")
        
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
        
        # Send the natural response
        whatsapp.send_message(from_number, result['response'])
        
        # Update extracted data if Claude provided values
        if result['extracted_data']:
            for key, value in result['extracted_data'].items():
                if value:  # Only update if there's a real value
                    state['extracted_data'][key] = value
        
        # Continue asking for missing info or finalize
        ask_for_missing_info(from_number)

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
            question = "📂 What category is this expense? (e.g., Meals, Travel, Supplies, Office)"
        elif field == 'cost_center':
            question = "🏢 What cost center should this be assigned to?"
        
        state['current_question'] = field
        whatsapp.send_message(from_number, question)
    else:
        # All info collected, finalize
        finalize_receipt(from_number)

def finalize_receipt(from_number):
    """Save receipt to Sheets and Drive"""
    state = conversation_states[from_number]
    
    try:
        whatsapp.send_message(from_number, "💾 Saving receipt...")
        
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
        confirmation = f"""✅ Receipt saved successfully!

📝 Summary:
• Merchant: {data.get('merchant_name', 'N/A')}
• Date: {data.get('date', 'N/A')}
• Amount: ${data.get('total_amount', 'N/A')}
• Category: {data.get('category', 'N/A')}
• Cost Center: {data.get('cost_center', 'N/A')}
• Payment: {data.get('payment_method', 'N/A')}

📊 Logged in Google Sheets

Send another receipt anytime!"""
        
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