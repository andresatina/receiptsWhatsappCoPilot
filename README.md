# Receipt Processing WhatsApp Agent

Automatically process receipt images sent via WhatsApp, extract data with Claude AI, and log to Google Sheets while filing images in Google Drive.

## Features

- ✅ Receive receipt images via WhatsApp (Kapso API)
- ✅ OCR extraction with Claude Vision
- ✅ Auto-categorize expenses
- ✅ Conversational follow-up for missing info (category, cost center)
- ✅ Duplicate detection
- ✅ Log to Google Sheets
- ✅ File images to Google Drive
- ✅ Multi-user support

## Setup

### 1. Share Google Resources

**CRITICAL - Do this first:**

Share with service account email: `atinareceiptswhatsapp@receipts-479317.iam.gserviceaccount.com`

1. **Google Sheet**: https://docs.google.com/spreadsheets/d/1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8/edit
   - Click "Share" → Add email → Give "Editor" access

2. **Google Drive Folder**: https://drive.google.com/drive/folders/1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut
   - Click "Share" → Add email → Give "Editor" access

### 2. Deploy to Railway

1. Go to: https://railway.app
2. Sign up with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Connect this repo
5. Add environment variables:
   ```
   KAPSO_API_KEY=YOUR_KAPSO_API_KEY
   WHATSAPP_PHONE_NUMBER=+12019792493
   WEBHOOK_VERIFY_TOKEN=receipt_agent_secret_2024
   CLAUDE_API_KEY=YOUR_CLAUDE_API_KEY
   GOOGLE_SHEET_ID=1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8
   GOOGLE_DRIVE_FOLDER_ID=1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut
   ```

6. Railway will auto-deploy and give you a URL (e.g., `https://your-app.railway.app`)

### 3. Configure Kapso Webhook

1. Go to: https://app.kapso.ai
2. Navigate to Settings → Webhooks
3. Add webhook URL: `https://your-app.railway.app/webhook`
4. Set verify token: `receipt_agent_secret_2024`
5. Save

## Testing Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run Flask app
python app.py
```

Use ngrok to expose local server:
```bash
ngrok http 5000
```

Then set Kapso webhook to your ngrok URL.

## How It Works

1. **User sends receipt image** → WhatsApp → Kapso
2. **Kapso webhook** → Your Flask app receives image
3. **Claude Vision** → Extracts merchant, date, amount, line items, payment
4. **Auto-categorization** → Smart expense category assignment
5. **Conversational flow** → Bot asks for category (if not auto-assigned) and cost center
6. **Duplicate check** → SHA256 hash prevents double-filing
7. **Google Drive** → Uploads image, gets shareable link
8. **Google Sheets** → Logs all data in structured format
9. **Confirmation** → Sends summary back to user

## Google Sheets Structure

| Timestamp | Merchant | Date | Amount | Category | Cost Center | Payment | Line Items | Drive URL | Hash | Submitted By |
|-----------|----------|------|--------|----------|-------------|---------|------------|-----------|------|--------------|

## Conversation Flow Example

```
User: [sends receipt image]
Bot: 🔍 Processing your receipt...
Bot: 📂 What category is this expense? (e.g., Meals, Travel, Supplies)
User: Meals
Bot: 🏢 What cost center should this be assigned to?
User: Marketing
Bot: 💾 Saving receipt...
Bot: ✅ Receipt saved successfully!
     
     📝 Summary:
     • Merchant: Starbucks
     • Date: 2024-11-25
     • Amount: $15.67
     • Category: Meals
     • Cost Center: Marketing
     • Payment: Credit Card
     
     📎 Filed in Google Drive
     📊 Logged in Google Sheets
```

## File Structure

```
receipt-agent/
├── app.py                  # Main Flask application
├── whatsapp_handler.py     # Kapso API integration
├── claude_handler.py       # Claude Vision OCR
├── sheets_handler.py       # Google Sheets logging
├── drive_handler.py        # Google Drive file storage
├── credentials.json        # Google service account (DO NOT COMMIT)
├── requirements.txt        # Python dependencies
├── Procfile               # Railway deployment config
├── .env                   # Environment variables (DO NOT COMMIT)
└── README.md             # This file
```

## Cost Estimate

- **Kapso**: Free tier (limited messages) or ~$10-30/month
- **Claude API**: ~$1-3 per 100 receipts (vision calls)
- **Railway**: ~$5-10/month for always-on server
- **Google APIs**: Free

**Total**: ~$15-40/month for production use

## Troubleshooting

### Webhook not receiving messages
- Check Railway logs: `railway logs`
- Verify Kapso webhook URL is correct
- Test with `/health` endpoint

### Google Sheets not updating
- Verify service account has Editor access
- Check Railway logs for errors
- Test Sheet ID is correct

### Claude errors
- Verify API key is valid
- Check Claude API status
- Ensure image is valid JPEG

## Support

For issues, check Railway logs or contact support.
