from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io
import os
import base64
import json

class DriveHandler:
    def __init__(self, credentials_path, folder_id):
        self.folder_id = folder_id
        
        # Set up credentials
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        
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
        
        self.service = build('drive', 'v3', credentials=credentials)
    
    def upload_image(self, image_data, filename):
        """Upload receipt image to Google Drive"""
        
        file_metadata = {
            'name': filename,
            'parents': [self.folder_id]
        }
        
        media = MediaInMemoryUpload(
            image_data,
            mimetype='image/jpeg',
            resumable=True
        )
        
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        # Make file accessible to anyone with link
        self.service.permissions().create(
            fileId=file['id'],
            body={
                'type': 'anyone',
                'role': 'reader'
            }
        ).execute()
        
        return file.get('webViewLink')