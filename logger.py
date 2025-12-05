"""
Logger Helper - Centralized logging for errors and events
"""

import os
import traceback
import psycopg2
from psycopg2.extras import Json
from datetime import datetime


class Logger:
    """Handles logging to PostgreSQL and Sentry"""
    
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        
        # Initialize Sentry for critical errors (optional)
        try:
            import sentry_sdk
            sentry_dsn = os.getenv('SENTRY_DSN')
            if sentry_dsn:
                sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.1)
                self.sentry_enabled = True
            else:
                self.sentry_enabled = False
        except ImportError:
            self.sentry_enabled = False
    
    def log_error(self, error_type, error_message, user_id=None, company_id=None, context=None, critical=False):
        """
        Log an error to database and optionally Sentry
        
        Args:
            error_type: 'ocr_failed', 'sheets_save_failed', 'api_error', etc
            error_message: Human-readable error message
            user_id: User ID (optional)
            company_id: Company ID (optional)
            context: Dict with additional context (receipt_url, extracted_data, etc)
            critical: If True, send to Sentry for immediate alert
        """
        stack = traceback.format_exc()
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO error_logs 
                   (user_id, company_id, error_type, error_message, stack_trace, context)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (user_id, company_id, error_type, error_message, stack, Json(context or {}))
            )
            
            conn.commit()
            conn.close()
            
            print(f"❌ ERROR LOGGED: {error_type} - {error_message}")
            
        except Exception as e:
            print(f"Failed to log error to database: {str(e)}")
        
        # Send critical errors to Sentry
        if critical and self.sentry_enabled:
            try:
                import sentry_sdk
                sentry_sdk.capture_message(f"{error_type}: {error_message}", level="error")
            except:
                pass
    
    def log_event(self, event_type, user_id, company_id, receipt_hash=None, 
                  merchant_name=None, amount=None, category=None, cost_center=None,
                  ocr_data=None, metadata=None):
        """
        Log a receipt event for analytics
        
        Args:
            event_type: 'conversation_started', 'receipt_uploaded', 'ocr_completed', 'receipt_saved'
            user_id: User ID
            company_id: Company ID
            receipt_hash: SHA256 hash of receipt image
            merchant_name: Merchant name
            amount: Receipt amount
            category: Category assigned
            cost_center: Cost center assigned
            ocr_data: Full Claude Vision extraction
            metadata: Additional context
        """
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO receipt_events 
                   (user_id, company_id, event_type, receipt_hash, merchant_name, 
                    amount, category, cost_center, ocr_data, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (user_id, company_id, event_type, receipt_hash, merchant_name,
                 amount, category, cost_center, Json(ocr_data or {}), Json(metadata or {}))
            )
            
            conn.commit()
            conn.close()
            
            print(f"📊 EVENT LOGGED: {event_type} - user:{user_id}, company:{company_id}")
            
        except Exception as e:
            print(f"Failed to log event to database: {str(e)}")
    
    def log_conversation_started(self, user_id, company_id):
        """Shortcut for logging conversation start"""
        self.log_event('conversation_started', user_id, company_id)
    
    def log_receipt_uploaded(self, user_id, company_id, receipt_hash):
        """Shortcut for logging receipt upload"""
        self.log_event('receipt_uploaded', user_id, company_id, receipt_hash=receipt_hash)
    
    def log_ocr_completed(self, user_id, company_id, receipt_hash, ocr_data):
        """Shortcut for logging OCR completion"""
        merchant = ocr_data.get('merchant_name')
        amount = ocr_data.get('total_amount')
        self.log_event('ocr_completed', user_id, company_id, 
                      receipt_hash=receipt_hash, 
                      merchant_name=merchant,
                      amount=amount,
                      ocr_data=ocr_data)
    
    def log_receipt_saved(self, user_id, company_id, receipt_hash, 
                         merchant_name, amount, category, cost_center):
        """Shortcut for logging successful receipt save"""
        self.log_event('receipt_saved', user_id, company_id,
                      receipt_hash=receipt_hash,
                      merchant_name=merchant_name,
                      amount=amount,
                      category=category,
                      cost_center=cost_center)


# Global instance
logger = Logger()
