from dotenv import load_dotenv
load_dotenv()

import os
from flask import Flask, request, jsonify
import hashlib
import json
import time
import posthog

from whatsapp_handler import WhatsAppHandler
from claude_handler import ClaudeHandler
from sheets_handler import SheetsHandler
from drive_handler import DriveHandler
from conversational_helper import conversational
from database_handler import DatabaseHandler
from management_handler import management_handler
from logger import logger
from alert_handler import alert_handler


app = Flask(__name__)

# Initialize PostHog
posthog.api_key = os.getenv('POSTHOG_API_KEY')
posthog.host = 'https://us.i.posthog.com'

# Initialize handlers
whatsapp = WhatsAppHandler(
    api_key=os.getenv('KAPSO_API_KEY'),
    phone_number=os.getenv('WHATSAPP_PHONE_NUMBER'),
    phone_number_id=os.getenv('WHATSAPP_PHONE_NUMBER_ID')
)
claude = ClaudeHandler(api_key=os.getenv('CLAUDE_API_KEY'))
db = DatabaseHandler()  # PostgreSQL handler

# Note: sheets and drive handlers are now created per-company, not globally

# Store conversation states in memory (temporary, per session only)
# Learned patterns now stored in PostgreSQL
conversation_states = {}


def get_user_state(phone_number):
    """Get or create user state - loads from database"""
    
    # ALWAYS refresh user data from database (to get latest company settings)
    user = db.get_or_create_user(phone_number)
    company_id = user['company_id']
    
    if phone_number not in conversation_states:
        # First time - create new state
        categories = db.get_categories(company_id)
        cost_centers = db.get_cost_centers(company_id)
        
        # Generate conversation ID for tracking
        conversation_id = f"{phone_number}_{int(time.time())}"
        
        conversation_states[phone_number] = {
            'state': 'new',
            'conversation_history': [],
            'user': user,  # ✅ Store user
            'company_id': company_id,
            'categories': [c['name'] for c in categories],
            'cost_centers': [cc['name'] for cc in cost_centers],
            'extracted_data': {},
            'asked_for_category': False,
            'asked_for_property': False,
            # NEW: Turn tracking
            'turn_number': 0,
            'conversation_id': conversation_id
        }
    else:
        # UPDATE: Refresh user data AND cost centers in existing state
        categories = db.get_categories(company_id)
        cost_centers = db.get_cost_centers(company_id)
    
        conversation_states[phone_number]['user'] = user
        conversation_states[phone_number]['company_id'] = company_id
        conversation_states[phone_number]['categories'] = [c['name'] for c in categories]
        conversation_states[phone_number]['cost_centers'] = [cc['name'] for cc in cost_centers]
    
    return conversation_states[phone_number]


def log_agent_action(state, action_phase, action_type, action_detail=None, 
                     duration_ms=None, success=True, metadata=None):
    """
    Helper to log agent actions with automatic turn increment
    """
    # Initialize if missing (for existing conversation states)
    if 'turn_number' not in state:
        state['turn_number'] = 0
    if 'conversation_id' not in state:
        state['conversation_id'] = f"{state['user']['phone_number']}_{int(time.time())}"
    
    # Increment turn for new actions (not observes)
    if action_phase == 'think':
        state['turn_number'] += 1
    
    logger.log_agent_action(
        user_id=state['user']['id'],
        company_id=state['company_id'],
        turn_number=state['turn_number'],
        conversation_id=state['conversation_id'],
        action_phase=action_phase,
        action_type=action_type,
        action_detail=action_detail,
        duration_ms=duration_ms,
        success=success,
        receipt_hash=state.get('image_hash'),
        metadata=metadata
    )


def save_learned_pattern(phone_number, merchant, items_text, category, cost_center):
    """Save learned pattern to database with item keywords"""
    
    # Get user's company_id
    state = get_user_state(phone_number)
    company_id = state['company_id']
    
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
        company_id=company_id,
        merchant=merchant,
        items_keywords=items_keywords,
        category_name=category,
        cost_center_name=cost_center
    )


@app.route('/clear-cache/<phone_number>', methods=['POST'])
def clear_cache(phone_number):
    """Clear conversation cache for a specific user"""
    try:
        if phone_number in conversation_states:
            del conversation_states[phone_number]
            return jsonify({
                'status': 'success',
                'message': f'Cache cleared for {phone_number}'
            })
        else:
            return jsonify({
                'status': 'success',
                'message': f'No cache found for {phone_number}'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/clear-all-cache', methods=['POST'])
def clear_all_cache():
    """Clear ALL conversation caches - use with caution"""
    try:
        count = len(conversation_states)
        conversation_states.clear()
        return jsonify({
            'status': 'success',
            'message': f'Cleared {count} user caches'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """Handle Kapso webhook for incoming WhatsApp messages"""
    print("🔔 WEBHOOK HIT!")
    print(f"Headers: {dict(request.headers)}")
    print(f"Body preview: {request.get_data()[:500]}")

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
        
        # Skip outbound messages (they don't have 'from' field)
        if 'from' not in message:
            return jsonify({'status': 'ok', 'note': 'outbound message, skipping'})
        
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
        user = state['user']
        
        # Clear conversation history for new receipt to prevent hallucination
        state['conversation_history'] = []
        
        # THINK: User sent receipt, need to process it
        log_agent_action(state, 'think', 'receipt_received', 
                        'User sent receipt image, will extract data')
        
        # Get company-specific sheets handler
        if not user.get('google_sheet_id'):
            whatsapp.send_message(from_number, "Your company doesn't have a Google Sheet configured yet. Please contact support.")
            return
        
        sheets = SheetsHandler(
            credentials_path='credentials.json',
            sheet_id=user['google_sheet_id']
        )
        
        # ACT: Download image
        start_time = time.time()
        image_url = message['kapso']['media_url']
        import requests
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        download_ms = int((time.time() - start_time) * 1000)
        
        # OBSERVE: Image downloaded successfully
        log_agent_action(state, 'observe', 'image_downloaded',
                        f'Downloaded {len(image_data)} bytes',
                        duration_ms=download_ms,
                        metadata={'image_size': len(image_data)})
        
        # Check for duplicate
        image_hash = hashlib.sha256(image_data).hexdigest()
        if db.is_duplicate(state['company_id'], image_hash):
            result = conversational.get_conversational_response(
                user_message="[User sent a duplicate receipt]",
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
            state['awaiting_duplicate_confirmation'] = True
            state['pending_image'] = {'data': image_data, 'hash': image_hash}
            
            # PostHog: Track duplicate
            posthog.capture(
                distinct_id=str(user['id']),
                event='receipt_duplicate',
                properties={
                    'company_id': state['company_id'],
                    'receipt_hash': image_hash
                },
                groups={'company': str(state['company_id'])}
            )
            return
        
        # Single "Processing..." message
        state['last_system_message'] = "[User just sent a receipt image, tell them you're processing it]"
        result = conversational.get_conversational_response(
            user_message="[User just sent a receipt image, tell them you're processing it]",
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])
        
        # Log receipt uploaded - Database
        logger.log_receipt_uploaded(
            user_id=state['user']['id'],
            company_id=state['company_id'],
            receipt_hash=image_hash
        )
        
        # PostHog: Track receipt uploaded
        posthog.capture(
            distinct_id=str(user['id']),
            event='receipt_uploaded',
            properties={
                'company_id': state['company_id'],
                'receipt_hash': image_hash,
                'image_size': len(image_data),
                'download_ms': download_ms
            },
            groups={'company': str(state['company_id'])}
        )
        
        # Check for consecutive event anomaly
        if alert_handler.check_consecutive_events(state['user']['id'], 'receipt_uploaded', threshold=3):
            alert_handler.log_anomaly(
                alert_type='consecutive_uploads',
                severity='warning',
                description=f"User {from_number} uploaded 3+ receipts without progress",
                user_id=state['user']['id'],
                company_id=state['company_id'],
                context={'phone_number': from_number}
            )
        
        # THINK: Need to extract receipt data
        log_agent_action(state, 'think', 'need_ocr', 'Will extract data from receipt image')
        
        # ACT: Extract data with OCR (with failure handling)
        start_time = time.time()
        try:
            extracted_data = claude.extract_receipt_data(image_data)
            ocr_ms = int((time.time() - start_time) * 1000)
            
            # OBSERVE: OCR completed
            log_agent_action(state, 'observe', 'ocr_completed',
                    f"Extracted: {extracted_data.get('merchant_name')} ${extracted_data.get('total_amount')}",
                    duration_ms=ocr_ms,
                    metadata=extracted_data)
            
            # Log OCR completed - Database
            logger.log_ocr_completed(
                user_id=state['user']['id'],
                company_id=state['company_id'],
                receipt_hash=image_hash,
                ocr_data=extracted_data
            )
            
            # PostHog: Track OCR completed
            posthog.capture(
                distinct_id=str(user['id']),
                event='ocr_completed',
                properties={
                    'company_id': state['company_id'],
                    'receipt_hash': image_hash,
                    'merchant': extracted_data.get('merchant_name', ''),
                    'amount': extracted_data.get('total_amount', 0),
                    'ocr_ms': ocr_ms
                },
                groups={'company': str(state['company_id'])}
            )
            
        except Exception as e:
            ocr_ms = int((time.time() - start_time) * 1000)
            
            # Log OCR failure - Database
            logger.log_error(
                error_type='ocr_failed',
                error_message=str(e),
                user_id=state['user']['id'],
                company_id=state['company_id'],
                context={'receipt_hash': image_hash},
                critical=True
            )
            
            # PostHog: Track error
            posthog.capture(
                distinct_id=str(user['id']),
                event='error',
                properties={
                    'error_type': 'ocr_failed',
                    'error_message': str(e),
                    'company_id': state['company_id'],
                    'receipt_hash': image_hash,
                    'ocr_ms': ocr_ms
                },
                groups={'company': str(state['company_id'])}
            )
            
            result = conversational.get_conversational_response(
                user_message="[Error: Could not read receipt image clearly]",
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
            return
        
        # Store extracted data and move to collecting info state
        state['state'] = 'collecting_info'
        state['image_data'] = image_data
        state['image_hash'] = image_hash
        state['extracted_data'] = extracted_data
        state['asked_for_category'] = False
        state['asked_for_property'] = False
        
        # Check if this is a bank transfer (no merchant name, has transaction ID)
        if not extracted_data.get('merchant_name') and extracted_data.get('total_amount'):
            state['state'] = 'collecting_beneficiary'
            state['last_system_message'] = f"[Bank transfer detected, amount ${extracted_data.get('total_amount')}. Ask who the payment was to.]"
            result = conversational.get_conversational_response(
                user_message=state['last_system_message'],
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
            return
        
        # Check for pattern match
        # Extract keywords from line_items for pattern matching
        items_keywords = [item['description'] for item in extracted_data.get('line_items', [])]
        
        patterns = db.find_matching_patterns(
            state['company_id'], 
            extracted_data.get('merchant_name', ''),
            items_keywords
        )
        
        # Get the best matching pattern (first in list)
        pattern = patterns[0] if patterns else None
        
        if pattern:
            state['suggested_pattern'] = pattern
            # Auto-apply the pattern
            if pattern.get('category'):
                state['extracted_data']['category'] = pattern['category']
            if pattern.get('cost_center'):
                state['extracted_data']['cost_center'] = pattern['cost_center']
        
        # Ask for missing info
        ask_for_missing_info(from_number, state)
        
    except Exception as e:
        print(f"Error handling receipt image: {str(e)}")
        import traceback
        traceback.print_exc()
        
        try:
            state = get_user_state(from_number)
            logger.log_error(
                error_type='receipt_processing_failed',
                error_message=str(e),
                user_id=state['user']['id'],
                company_id=state['company_id']
            )
        except:
            pass
        
        whatsapp.send_message(from_number, "Sorry, I had trouble processing that image. Please try sending it again.")


def ask_for_missing_info(from_number, state):
    """Ask user for any missing receipt info (category or cost center)"""
    
    extracted_data = state['extracted_data']
    has_category = bool(extracted_data.get('category'))
    
    # Check if company requires cost center
    requires_cost_center = state['user'].get('requires_cost_center', True)
    has_cost_center = True if not requires_cost_center else bool(extracted_data.get('cost_center'))
    
    # Determine what to ask for
    if not has_category:
        state['last_system_message'] = "[Receipt processed, ask for category only]"
    elif not has_cost_center:
        state['last_system_message'] = "[Receipt processed, ask for cost_center only]"
    else:
        # Have everything - go to confirmation
        state['state'] = 'awaiting_confirmation'
        show_confirmation(from_number, state)
        return
    
    result = conversational.get_conversational_response(
        user_message=state['last_system_message'],
        conversation_state=state
    )
    whatsapp.send_message(from_number, result['response'])


def handle_text_response(from_number, text):
    """Handle text message from user"""
    
    state = get_user_state(from_number)
    user = state['user']
    
    # Handle /manage command - enter management mode
    if text.strip().lower() == '/manage':
        state['state'] = 'managing'
        state['pending_management_action'] = None
        cost_center_label = user.get('cost_center_label', 'property/unit')
        term = cost_center_label.split('/')[0]
        
        whatsapp.send_message(from_number, f"🔧 Management mode. You can add, delete, or list {term}s and categories. Say 'done' when finished.")
        return
    
    # Handle management mode
    if state.get('state') == 'managing':
        response, should_exit = management_handler.handle_management(text, state, db)
        whatsapp.send_message(from_number, response)
        if should_exit:
            state['state'] = 'new'
            # Refresh cost centers after management changes
            company_id = state['company_id']
            cost_centers = db.get_cost_centers(company_id)
            state['cost_centers'] = [cc['name'] for cc in cost_centers]
            categories = db.get_categories(company_id)
            state['categories'] = [c['name'] for c in categories]
        return
    
    # If user is new (no receipt sent yet)
    if state.get('state') == 'new':
        # Log conversation started - Database
        logger.log_conversation_started(
            user_id=state['user']['id'],
            company_id=state['company_id']
        )
        
        # PostHog: Track conversation started
        posthog.capture(
            distinct_id=str(user['id']),
            event='conversation_started',
            properties={
                'company_id': state['company_id']
            },
            groups={'company': str(state['company_id'])}
        )
        
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])
        return
    
    # Handle duplicate confirmation
    if state.get('awaiting_duplicate_confirmation'):
        if text.lower() in ['yes', 'y', 'si', 'sí', 'sim']:
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
    
    # Handle bank transfer beneficiary collection
    if state.get('state') == 'collecting_beneficiary':
        state['extracted_data']['merchant_name'] = text
        state['state'] = 'collecting_info'
        state['last_system_message'] = "[Receipt processed]"
        ask_for_missing_info(from_number, state)
        return
    
    # Handle confirmation step - NEW
    if state.get('state') == 'awaiting_confirmation':
        text_lower = text.lower().strip()
        
        # User confirmed - save the receipt
        if text_lower in ['yes', 'y', 'si', 'sí', 'sim', 'correct', 'correcto', 'ok', 'sip']:
            # Save learned pattern
            merchant = state['extracted_data'].get('merchant_name', '')
            items = state['extracted_data'].get('items', '')
            category = state['extracted_data'].get('category')
            cost_center = state['extracted_data'].get('cost_center')
            
            if merchant and category and cost_center:
                save_learned_pattern(from_number, merchant, items, category, cost_center)
            
            finalize_receipt(from_number)
            return
        
        # User said no - ask what to fix
        elif text_lower in ['no', 'n', 'não', 'nao']:
            state['state'] = 'fixing_data'
            state['last_system_message'] = "[User said data is incorrect, ask what needs to be fixed]"
            result = conversational.get_conversational_response(
                user_message=state['last_system_message'],
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
            return
        
        # Unclear response - ask again
        else:
            result = conversational.get_conversational_response(
                user_message=text,
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
            return
    
    # Handle fixing data after user said "no" to confirmation - NEW
    if state.get('state') == 'fixing_data':
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state
        )
        
        # Check if user provided corrections via JSON
        if result['extracted_data']:
            for key, value in result['extracted_data'].items():
                if value and key not in ['skip_category', 'skip_cost_center']:
                    state['extracted_data'][key] = value
            # After getting corrections, show confirmation again
            state['state'] = 'awaiting_confirmation'
            show_confirmation(from_number, state)
            return
        
        # Send response (asking what to fix)
        whatsapp.send_message(from_number, result['response'])
        return
    
    # Handle collecting info
    if state.get('state') == 'collecting_info':
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state
        )
        
        # Check if user confirmed skip
        if result['extracted_data'].get('skip_category'):
            state['extracted_data']['category'] = 'Uncategorized'
        if result['extracted_data'].get('skip_cost_center'):
            state['extracted_data']['cost_center'] = 'Unassigned'
        
        # Update extracted data if Claude provided values
        if result['extracted_data']:
            for key, value in result['extracted_data'].items():
                if value and key not in ['skip_category', 'skip_cost_center']:
                    state['extracted_data'][key] = value
        
        # Check what we have now
        has_category = bool(state['extracted_data'].get('category'))
        requires_cost_center = state['user'].get('requires_cost_center', True)
        has_property = True if not requires_cost_center else bool(state['extracted_data'].get('cost_center'))
        
        # If we have everything, show confirmation instead of saving directly
        if has_category and has_property:
            state['state'] = 'awaiting_confirmation'
            show_confirmation(from_number, state)
        else:
            whatsapp.send_message(from_number, result['response'])
            if has_category and not has_property and not state.get('asked_for_property'):
                state['asked_for_property'] = True


def show_confirmation(from_number, state):
    """Show receipt summary and ask for confirmation before saving"""
    state['last_system_message'] = "[Show confirmation summary and ask if correct]"
    result = conversational.get_conversational_response(
        user_message=state['last_system_message'],
        conversation_state=state
    )
    whatsapp.send_message(from_number, result['response'])


def finalize_receipt(from_number):
    """Save receipt to Sheets"""
    state = conversation_states[from_number]
    user = state['user']
    
    try:
        if not user.get('google_sheet_id'):
            whatsapp.send_message(from_number, "Your company doesn't have a Google Sheet configured yet. Please contact support.")
            return
        
        sheets = SheetsHandler(
            credentials_path='credentials.json',
            sheet_id=user['google_sheet_id']
        )
        
        # "Saving..." message
        state['last_system_message'] = "[Tell user you're saving the receipt now]"
        result = conversational.get_conversational_response(
            user_message="[Tell user you're saving the receipt now]",
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])
        
        # Save to Sheets with retry logic
        state['extracted_data']['submitted_by'] = user.get('name', from_number)
        
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
        from googleapiclient.errors import HttpError
        import socket
        
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((HttpError, socket.timeout, ConnectionError)),
            reraise=True
        )
        def save_to_sheets_with_retry():
            return sheets.add_receipt(state['extracted_data'])
        
        save_to_sheets_with_retry()
        
        # Log receipt saved
        logger.log_receipt_saved(
            user_id=state['user']['id'],
            company_id=state['company_id'],
            receipt_hash=state['image_hash'],
            merchant_name=state['extracted_data'].get('merchant_name', ''),
            amount=state['extracted_data'].get('total_amount', 0),
            category=state['extracted_data'].get('category', ''),
            cost_center=state['extracted_data'].get('cost_center', '')
        )
        
        # PostHog: Track receipt saved
        posthog.capture(
            distinct_id=str(user['id']),
            event='receipt_saved',
            properties={
                'company_id': state['company_id'],
                'receipt_hash': state['image_hash'],
                'merchant': state['extracted_data'].get('merchant_name', ''),
                'amount': state['extracted_data'].get('total_amount', 0),
                'category': state['extracted_data'].get('category', ''),
                'cost_center': state['extracted_data'].get('cost_center', '')
            },
            groups={'company': str(state['company_id'])}
        )
        
        # Success message
        state['last_system_message'] = "[Receipt saved successfully]"
        result = conversational.get_conversational_response(
            user_message="[Receipt saved successfully]",
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])
        
    except Exception as e:
        logger.log_error(
            error_type='sheets_save_failed',
            error_message=str(e),
            user_id=state['user']['id'],
            company_id=state['company_id'],
            context={'extracted_data': state.get('extracted_data')},
            critical=True
        )
        
        posthog.capture(
            distinct_id=str(user['id']),
            event='error',
            properties={
                'error_type': 'sheets_save_failed',
                'error_message': str(e),
                'company_id': state['company_id']
            },
            groups={'company': str(state['company_id'])}
        )
        
        whatsapp.send_message(from_number, f"Sorry, there was an error saving your receipt: {str(e)}")
        print(f"Error saving receipt: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Clear state
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


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)