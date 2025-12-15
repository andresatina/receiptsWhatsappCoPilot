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

app = Flask(__name__)

# Initialize PostHog
posthog.api_key = os.getenv('POSTHOG_API_KEY')
posthog.host = 'https://us.i.posthog.com'

# Initialize handlers
whatsapp = WhatsAppHandler(
    api_key=os.getenv('KAPSO_API_KEY'),
    phone_number=os.getenv('WHATSAPP_PHONE_NUMBER')
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
    
    Args:
        state: Conversation state dict
        action_phase: 'think', 'act', 'observe'
        action_type: Action identifier (e.g., 'ocr_extract', 'ask_category')
        action_detail: Human-readable description
        duration_ms: Duration in milliseconds
        success: Whether action succeeded
        metadata: Additional context
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
        
        # IMPROVEMENT #3: Single "Processing..." message (not multiple)
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
        
        # THINK: Need to extract receipt data
        log_agent_action(state, 'think', 'need_ocr', 'Will extract data from receipt image')
        
        # ACT: Extract data with OCR
        start_time = time.time()
        extracted_data = claude.extract_receipt_data(image_data)
        ocr_ms = int((time.time() - start_time) * 1000)
        
        # OBSERVE: OCR completed
        log_agent_action(state, 'observe', 'ocr_completed',
                f"Extracted: {extracted_data.get('merchant_name')} ${extracted_data.get('total_amount')}",
                duration_ms=ocr_ms,
                metadata=extracted_data)  # ✅ Store complete object with correct field names
        
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
                'merchant': extracted_data.get('merchant_name'),
                'amount': extracted_data.get('total_amount'),
                'ocr_ms': ocr_ms,
                'is_bank_transfer': extracted_data.get('is_bank_transfer', False)
            },
            groups={'company': str(state['company_id'])}
        )
        
        # DEBUG: Log what was actually extracted
        print(f"🔍 OCR EXTRACTED DATA:")
        print(f"   Merchant: {extracted_data.get('merchant_name')}")
        print(f"   Amount: {extracted_data.get('total_amount')}")
        print(f"   Full data: {json.dumps(extracted_data, indent=2)}")
        
        # Check if it's a bank transfer (explicit flag)
        if extracted_data.get('is_bank_transfer'):
            # Bank transfer detected - ask for beneficiary
            state['state'] = 'collecting_beneficiary'
            state['image_data'] = image_data
            state['image_hash'] = image_hash
            state['extracted_data'] = extracted_data
            state['last_system_message'] = "[Bank transfer detected, ask who it was paid to]"
            state['asked_for_category'] = False
            state['asked_for_property'] = False
            
            result = conversational.get_conversational_response(
                user_message="[Bank transfer detected, ask who it was paid to]",
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
            return
        
        # CRITICAL: If merchant is None/empty, treat as bank transfer (fallback)
        if not extracted_data.get('merchant_name'):
            state['state'] = 'collecting_beneficiary'
            state['image_data'] = image_data
            state['image_hash'] = image_hash
            state['extracted_data'] = extracted_data
            state['last_system_message'] = "[Bank transfer detected, ask who it was paid to]"
            state['asked_for_category'] = False
            state['asked_for_property'] = False
            
            result = conversational.get_conversational_response(
                user_message="[Bank transfer detected, ask who it was paid to]",
                conversation_state=state
            )
            whatsapp.send_message(from_number, result['response'])
            return
        
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
        # Log error - Database
        state = get_user_state(from_number)
        logger.log_error(
            error_type='receipt_processing_failed',
            error_message=str(e),
            user_id=state['user']['id'],
            company_id=state['company_id'],
            context={'image_url': message.get('kapso', {}).get('media_url')},
            critical=True
        )
        
        # PostHog: Track error
        posthog.capture(
            distinct_id=str(state['user']['id']),
            event='error',
            properties={
                'error_type': 'receipt_processing_failed',
                'error_message': str(e),
                'company_id': state['company_id']
            },
            groups={'company': str(state['company_id'])}
        )
        
        print(f"Error handling receipt image: {str(e)}")
        import traceback
        traceback.print_exc()
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
    
    # Skip cost center if company doesn't require it
    requires_cost_center = state['user'].get('requires_cost_center', True)
    has_property = True if not requires_cost_center else bool(state['extracted_data'].get('cost_center'))
    
    # If we have both, finalize immediately
    if has_category and has_property:
        finalize_receipt(from_number)
        return
    
    # Check for matching patterns in database
    merchant = state['extracted_data'].get('merchant_name', '')
    line_items = state['extracted_data'].get('line_items', [])
    items_text = '\n'.join([item.get('description', '') for item in line_items]) if line_items else ''
    
    if merchant:
        # Extract keywords from current receipt items (if available)
        items_keywords = []
        if items_text:
            import re
            words = re.split(r'[\n,\$\d\.\s]+', items_text.lower())
            items_keywords = [w.strip() for w in words if len(w.strip()) > 2]
            items_keywords = list(set(items_keywords))[:10]
        
        # Find matching patterns using company_id
        company_id = state['company_id']
        matches = db.find_matching_patterns(company_id, merchant, items_keywords)
        
        if matches and matches[0]['similarity'] >= 60:
            # Good match found - add to state for conversational AI to use
            best_match = matches[0]
            state['suggested_pattern'] = {
                'category': best_match['category_name'],
                'cost_center': best_match['cost_center_name'],
                'similarity': best_match['similarity']
            }
            
            # PostHog: Track pattern matched
            posthog.capture(
                distinct_id=str(state['user']['id']),
                event='pattern_matched',
                properties={
                    'company_id': state['company_id'],
                    'merchant': merchant,
                    'similarity': best_match['similarity'],
                    'category': best_match['category_name'],
                    'cost_center': best_match['cost_center_name']
                },
                groups={'company': str(state['company_id'])}
            )
    
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
    user = state['user']
    
    # Handle /manage command - enter management mode
    if text.strip().lower() == '/manage':
        state['state'] = 'managing'
        state['pending_management_action'] = None
        cost_center_label = user.get('cost_center_label', 'property/unit')
        term = cost_center_label.split('/')[0]  # "property", "job", etc.
        
        whatsapp.send_message(from_number, f"🔧 Management mode. You can add, delete, or list {term}s and categories. Say 'done' when finished.")
        return
    
    # Handle management mode
    if state.get('state') == 'managing':
        response, should_exit = management_handler.handle_management(text, state, db)
        whatsapp.send_message(from_number, response)
        if should_exit:
            state['state'] = 'new'
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
    
    # Handle bank transfer beneficiary collection
    if state.get('state') == 'collecting_beneficiary':
        # User told us who the payment was to
        state['extracted_data']['merchant_name'] = text
        state['state'] = 'collecting_info'
        state['last_system_message'] = "[Receipt processed]"
        
        # Now proceed with normal flow
        ask_for_missing_info(from_number, state)
        return
    
    # Handle collecting info
    if state.get('state') == 'collecting_info':
        # IMPROVEMENT #4: Get conversational response and extract data
        result = conversational.get_conversational_response(
            user_message=text,
            conversation_state=state
        )
        
        # Check if user wants to skip (Claude detected skip intent)
        if result['extracted_data'].get('skip'):
            has_category = bool(state['extracted_data'].get('category'))
            requires_cost_center = state['user'].get('requires_cost_center', True)
            
            if not has_category:
                state['extracted_data']['category'] = 'Uncategorized'
            elif requires_cost_center and not state['extracted_data'].get('cost_center'):
                state['extracted_data']['cost_center'] = 'Unassigned'
            
            # Send Claude's acknowledgment response
            whatsapp.send_message(from_number, result['response'])
            
            # Check if we now have everything
            has_category = bool(state['extracted_data'].get('category'))
            has_property = True if not requires_cost_center else bool(state['extracted_data'].get('cost_center'))
            
            if has_category and has_property:
                finalize_receipt(from_number)
            else:
                ask_for_missing_info(from_number, state)
            return
        
        # Update extracted data if Claude provided values
        if result['extracted_data']:
            for key, value in result['extracted_data'].items():
                if value:
                    state['extracted_data'][key] = value
        
        # Check what we have now
        has_category = bool(state['extracted_data'].get('category'))
        
        # Skip cost center if company doesn't require it
        requires_cost_center = state['user'].get('requires_cost_center', True)
        has_property = True if not requires_cost_center else bool(state['extracted_data'].get('cost_center'))
        
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
    user = state['user']
    
    try:
        # Get company-specific sheets handler
        if not user.get('google_sheet_id'):
            whatsapp.send_message(from_number, "Your company doesn't have a Google Sheet configured yet. Please contact support.")
            return
        
        sheets = SheetsHandler(
            credentials_path='credentials.json',
            sheet_id=user['google_sheet_id']
        )
        
        # IMPROVEMENT #3: Single short "Saving..." message
        state['last_system_message'] = "[Tell user you're saving the receipt now]"
        result = conversational.get_conversational_response(
            user_message="[Tell user you're saving the receipt now]",
            conversation_state=state
        )
        whatsapp.send_message(from_number, result['response'])
        
        # Save to Sheets with retry logic
        state['extracted_data']['submitted_by'] = user.get('name', from_number)
        
        # Retry wrapper for Google Sheets API
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
        from googleapiclient.errors import HttpError
        import socket
        
        @retry(
            stop=stop_after_attempt(3),  # Try 3 times
            wait=wait_exponential(multiplier=1, min=2, max=10),  # 2s, 4s, 8s
            retry=retry_if_exception_type((HttpError, socket.timeout, ConnectionError)),
            reraise=True
        )
        def save_to_sheets_with_retry():
            return sheets.add_receipt(state['extracted_data'])
        
        save_to_sheets_with_retry()
        
        # Log receipt saved - Database
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
        
        # IMPROVEMENT #2: Concise success message with summary
        state['last_system_message'] = "[Receipt saved successfully]"
        result = conversational.get_conversational_response(
            user_message="[Receipt saved successfully]",
            conversation_state=state
        )
        
        whatsapp.send_message(from_number, result['response'])
        
    except Exception as e:
        # Log error - Database
        logger.log_error(
            error_type='sheets_save_failed',
            error_message=str(e),
            user_id=state['user']['id'],
            company_id=state['company_id'],
            context={'extracted_data': state.get('extracted_data')},
            critical=True
        )
        
        # PostHog: Track error
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


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)