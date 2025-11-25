# 🎯 Quick Start - Receipt Agent

## What You Have

A complete WhatsApp receipt processing agent that:
- Receives receipt photos via WhatsApp
- Extracts data with Claude AI (merchant, date, amount, items)
- Auto-categorizes expenses
- Asks for missing info (category, cost center)
- Detects duplicates
- Files images to Google Drive
- Logs everything to Google Sheets

---

## ⚡ 3-Step Deployment

### 1️⃣ Share Google Resources (2 minutes)

Share with: `atinareceiptswhatsapp@receipts-479317.iam.gserviceaccount.com`

✅ **Google Sheet**: https://docs.google.com/spreadsheets/d/1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8/edit
- Click Share → Add email → Editor access

✅ **Google Drive Folder**: https://drive.google.com/drive/folders/1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut
- Click Share → Add email → Editor access

---

### 2️⃣ Deploy to Railway (5 minutes)

1. Go to https://railway.app
2. Login with GitHub
3. New Project → Deploy from GitHub
4. Push this code to a GitHub repo
5. Select the repo
6. Add these environment variables:

```
KAPSO_API_KEY=YOUR_KAPSO_API_KEY
WHATSAPP_PHONE_NUMBER=+12019792493
WEBHOOK_VERIFY_TOKEN=receipt_agent_secret_2024
CLAUDE_API_KEY=YOUR_CLAUDE_API_KEY
GOOGLE_SHEET_ID=1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8
GOOGLE_DRIVE_FOLDER_ID=1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut
```

7. Generate Domain → Copy your URL

---

### 3️⃣ Configure Kapso Webhook (2 minutes)

1. Go to https://app.kapso.ai
2. Settings → Webhooks
3. Add webhook:
   - URL: `https://your-railway-url.railway.app/webhook`
   - Verify Token: `receipt_agent_secret_2024`
4. Save

---

## ✅ Test It

Send a receipt photo to: **+12019792493**

The bot will:
1. "🔍 Processing your receipt..."
2. Ask for category
3. Ask for cost center
4. "💾 Saving receipt..."
5. "✅ Receipt saved successfully!" + summary

---

## 📁 Project Files

- `app.py` - Main Flask server
- `whatsapp_handler.py` - Kapso API integration
- `claude_handler.py` - Receipt OCR with Claude
- `sheets_handler.py` - Google Sheets logging
- `drive_handler.py` - Google Drive file storage
- `requirements.txt` - Dependencies
- `Procfile` - Railway config
- `credentials.json` - Google service account

---

## 📖 Full Documentation

- `README.md` - Complete overview and usage
- `DEPLOYMENT.md` - Detailed deployment guide with troubleshooting

---

## 💰 Costs

- Railway: ~$5-10/month
- Kapso: ~$10-30/month
- Claude API: ~$1-3 per 100 receipts
- Google: Free

**Total**: ~$15-40/month

---

## 🐛 Troubleshooting

**Webhook not working?**
- Check Railway logs
- Verify Kapso webhook URL
- Test `/health` endpoint

**Google not updating?**
- Confirm you shared with service account
- Check permissions (Editor)
- Verify IDs are correct

**Need help?**
Check Railway logs or see DEPLOYMENT.md for detailed troubleshooting.

---

## 🎉 That's It!

Your receipt agent is ready. Just deploy and start sending receipts!
