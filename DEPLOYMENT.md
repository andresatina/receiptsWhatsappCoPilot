# 🚀 Deployment Guide - Step by Step

## ✅ Pre-Deployment Checklist

### 1. Share Google Resources (CRITICAL!)

You MUST share these with: `atinareceiptswhatsapp@receipts-479317.iam.gserviceaccount.com`

**Google Sheet:**
1. Open: https://docs.google.com/spreadsheets/d/1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8/edit
2. Click "Share" button (top right)
3. Add email: `atinareceiptswhatsapp@receipts-479317.iam.gserviceaccount.com`
4. Set permission: "Editor"
5. Click "Send"

**Google Drive Folder:**
1. Open: https://drive.google.com/drive/folders/1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut
2. Click "Share" button
3. Add email: `atinareceiptswhatsapp@receipts-479317.iam.gserviceaccount.com`
4. Set permission: "Editor"
5. Click "Send"

---

## 📦 Deploy to Railway

### Step 1: Create Railway Account
1. Go to: https://railway.app
2. Click "Login with GitHub"
3. Authorize Railway

### Step 2: Create New Project
1. Click "New Project"
2. Select "Deploy from GitHub repo"
3. If this is your first time:
   - Click "Configure GitHub App"
   - Select the repo where you pushed this code
4. Select the `receipt-agent` repository

### Step 3: Configure Environment Variables
1. Click on your deployed service
2. Go to "Variables" tab
3. Click "Add Variable" and add each of these:

```
KAPSO_API_KEY
YOUR_KAPSO_API_KEY

WHATSAPP_PHONE_NUMBER
+12019792493

WEBHOOK_VERIFY_TOKEN
receipt_agent_secret_2024

CLAUDE_API_KEY
YOUR_CLAUDE_API_KEY

GOOGLE_SHEET_ID
1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8

GOOGLE_DRIVE_FOLDER_ID
1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut
```

### Step 4: Add Google Credentials
**IMPORTANT:** Railway needs the credentials.json file.

**Option A: Use Railway CLI (Recommended)**
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to your project
railway link

# Add credentials file
railway variables set GOOGLE_APPLICATION_CREDENTIALS="$(cat credentials.json | base64)"
```

**Option B: Manual (in code)**
The `credentials.json` file is already in the repo (excluded from git via .gitignore). 
Railway will need access to it. You may need to:
1. Create a private repo
2. Include credentials.json (securely)
3. Or use Railway's file storage

### Step 5: Deploy
1. Railway will auto-deploy on push
2. Wait for build to complete (~2-3 minutes)
3. Click on your service → "Settings" → Generate Domain
4. Copy your Railway URL (e.g., `https://receipt-agent-production.up.railway.app`)

---

## 🔗 Configure Kapso Webhook

### Step 1: Login to Kapso
1. Go to: https://app.kapso.ai
2. Login with your account

### Step 2: Add Webhook
1. Navigate to: Settings → Webhooks (or similar)
2. Click "Add Webhook" or "Configure Webhook"
3. Enter:
   - **Webhook URL**: `https://your-railway-url.railway.app/webhook`
   - **Verify Token**: `receipt_agent_secret_2024`
4. Save

### Step 3: Test
1. Send a test message to your WhatsApp number: `+12019792493`
2. Check Railway logs:
   - Go to Railway dashboard
   - Click on your service
   - View "Logs" tab
3. You should see webhook events coming in

---

## ✅ Verify It's Working

### Test 1: Health Check
Open in browser: `https://your-railway-url.railway.app/health`

Should return:
```json
{"status": "healthy"}
```

### Test 2: Send Receipt
1. Save this test receipt image: [use any receipt photo]
2. Send it via WhatsApp to: `+12019792493`
3. Bot should respond with: "🔍 Processing your receipt..."

### Test 3: Check Logs
Railway dashboard → Your service → Logs

Look for:
- "Received webhook: ..."
- "Processing your receipt..."
- Claude API calls
- Google Sheets/Drive updates

---

## 🐛 Troubleshooting

### Issue: Webhook not receiving messages
**Solution:**
1. Verify Kapso webhook URL is exactly: `https://your-url.railway.app/webhook`
2. Check Railway logs for incoming requests
3. Test `/health` endpoint works

### Issue: Google Sheets not updating
**Solution:**
1. Verify you shared Sheet with service account email
2. Check Sheet ID is correct
3. Look for errors in Railway logs

### Issue: Google Drive upload fails
**Solution:**
1. Verify you shared Drive folder with service account email
2. Check folder ID is correct
3. Ensure service account has "Editor" permission

### Issue: Claude API errors
**Solution:**
1. Verify API key is valid at https://console.anthropic.com
2. Check you have API credits
3. Review error message in Railway logs

### Issue: Railway build fails
**Solution:**
1. Check `requirements.txt` has all dependencies
2. Ensure `Procfile` exists
3. Verify Python version compatibility

---

## 📊 Monitor Your Agent

### Railway Dashboard
- **Logs**: Real-time logs of all activity
- **Metrics**: CPU, memory, request count
- **Deployments**: History of deploys

### Check Data
- **Google Sheets**: View all logged receipts
- **Google Drive**: Browse filed receipt images

---

## 💰 Costs

- **Railway**: $5 free credit/month, then ~$5-10/month
- **Kapso**: Free tier or ~$10-30/month
- **Claude API**: ~$1-3 per 100 receipts
- **Google**: Free

**Total estimated**: $15-40/month for production use

---

## 🎉 You're Done!

Your receipt processing agent is now live and ready to use!

**Send a receipt to**: `+12019792493`

The bot will:
1. Extract merchant, date, amount, items
2. Ask for category and cost center
3. File image to Google Drive
4. Log everything to Google Sheets
5. Send confirmation

---

## Next Steps

- Add more team members (just share the WhatsApp number)
- Customize categories in `claude_handler.py`
- Add more fields to track
- Create reports/dashboards from Google Sheets data
