from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime
import os
import base64
import json

class SheetsHandler:
    def __init__(self, credentials_path, sheet_id):
        self.sheet_id = sheet_id
        
        # Set up credentials
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        
        # Check if base64 credentials exist (for Railway deployment)
        if os.getenv('GOOGLE_CREDENTIALS_BASE64'):
            creds_json = base64.b64decode(os.getenv('GOOGLE_CREDENTIALS_BASE64')).decode('utf-8')
            creds_dict = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
        else:
            # Use file (for local development)
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=SCOPES
            )
        
        self.service = build('sheets', 'v4', credentials=credentials)
        self.sheet = self.service.spreadsheets()
        
        # Initialize sheet with headers if needed
        self._ensure_headers()
    
    def _ensure_headers(self):
        """Ensure the sheet has proper headers"""
        try:
            # Read first row
            result = self.sheet.values().get(
                spreadsheetId=self.sheet_id,
                range='A1:I1'
            ).execute()
            
            values = result.get('values', [])
            
            # If no headers, add them
            if not values:
                headers = [
                    'Timestamp',
                    'Merchant Name',
                    'Date',
                    'Total Amount',
                    'Category',
                    'Cost Center',
                    'Payment Method',
                    'Line Items',
                    'Submitted By'
                ]
                
                self.sheet.values().update(
                    spreadsheetId=self.sheet_id,
                    range='A1:I1',
                    valueInputOption='RAW',
                    body={'values': [headers]}
                ).execute()
        except Exception as e:
            print(f"Error ensuring headers: {str(e)}")
    
    def add_receipt(self, data):
        """Add receipt data to Google Sheets"""
        
        # Format line items
        line_items_str = ""
        if 'line_items' in data and data['line_items']:
            line_items_str = "; ".join([
                f"{item['description']}: ${item['amount']}"
                for item in data['line_items']
            ])
        
        # Prepare row data
        row = [
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            data.get('merchant_name', ''),
            data.get('date', ''),
            data.get('total_amount', ''),
            data.get('category', ''),
            data.get('cost_center', ''),
            data.get('payment_method', ''),
            line_items_str,
            data.get('submitted_by', '')
        ]
        
        # Append to sheet
        self.sheet.values().append(
            spreadsheetId=self.sheet_id,
            range='A:I',
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body={'values': [row]}
        ).execute()