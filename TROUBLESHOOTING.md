# 🔧 Troubleshooting Guide

## 🚨 Common Issues & Solutions

---

### Issue 1: Webhook Not Receiving Messages

**Symptoms:**
- Send receipt to WhatsApp, no response
- Railway logs show no incoming requests

**Solutions:**

✅ **Check Kapso Webhook Configuration**
1. Go to https://app.kapso.ai
2. Settings → Webhooks
3. Verify URL is exactly: `https://your-railway-url.railway.app/webhook`
4. Verify token is: `receipt_agent_secret_2024`
5. Re-save webhook

✅ **Test Health Endpoint**
```bash
curl https://your-railway-url.railway.app/health
```
Should return: `{"status":"healthy"}`

✅ **Check Railway Logs**
1. Railway dashboard → Your service → Logs
2. Look for: "Received webhook: ..."
3. If no logs → webhook not reaching server

✅ **Verify Railway Deployment**
- Ensure app is deployed and running
- Check for build errors
- Confirm PORT environment variable is set

---

### Issue 2: Google Sheets Not Updating

**Symptoms:**
- Bot says "Receipt saved!" but sheet is empty
- Error in logs about Google API

**Solutions:**

✅ **Verify Sharing**
1. Open your Google Sheet
2. Click "Share" button
3. Confirm `atinareceiptswhatsapp@receipts-479317.iam.gserviceaccount.com` is listed
4. Confirm permission is "Editor" (not "Viewer")

✅ **Check Sheet ID**
```
URL: https://docs.google.com/spreadsheets/d/1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8/edit
                                           ↑ This is the Sheet ID ↑
```
Verify in Railway env vars: `GOOGLE_SHEET_ID=1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8`

✅ **Test Credentials**
Add to Railway logs:
```python
# In sheets_handler.py __init__
print(f"Attempting to access sheet: {sheet_id}")
```

✅ **Check API Errors**
Railway logs will show:
- `403 Forbidden` → Sharing issue
- `404 Not Found` → Wrong Sheet ID
- `401 Unauthorized` → Credentials issue

---

### Issue 3: Google Drive Upload Fails

**Symptoms:**
- Error: "Failed to upload to Drive"
- Sheets update but no Drive link

**Solutions:**

✅ **Verify Folder Sharing**
1. Open Google Drive folder
2. Right-click → Share
3. Confirm service account email is added
4. Confirm "Editor" permission

✅ **Check Folder ID**
```
URL: https://drive.google.com/drive/folders/1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut
                                           ↑ This is the Folder ID ↑
```
Verify in Railway: `GOOGLE_DRIVE_FOLDER_ID=1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut`

✅ **Test Manually**
```python
# Quick test script
from drive_handler import DriveHandler
import os

drive = DriveHandler('credentials.json', os.getenv('GOOGLE_DRIVE_FOLDER_ID'))
with open('test.txt', 'w') as f:
    f.write('test')
url = drive.upload_image(open('test.txt', 'rb').read(), 'test.txt')
print(f"Uploaded: {url}")
```

---

### Issue 4: Claude API Errors

**Symptoms:**
- "Error processing receipt"
- Bot doesn't extract data

**Solutions:**

✅ **Verify API Key**
1. Go to https://console.anthropic.com
2. Check API key is active
3. Confirm you have credits

✅ **Check Rate Limits**
- Claude API has rate limits
- Wait a minute and retry
- Upgrade plan if needed

✅ **Test Image Quality**
- Ensure image is clear
- Receipt should be well-lit
- Try with a different receipt

✅ **Check Error Message**
Railway logs will show specific Claude error:
- `401` → Invalid API key
- `429` → Rate limit exceeded
- `500` → Claude service issue

---

### Issue 5: Kapso API Issues

**Symptoms:**
- Can't send messages
- Can't download images

**Solutions:**

✅ **Verify Kapso API Key**
1. Go to https://app.kapso.ai
2. Settings → API Keys
3. Confirm key matches Railway env var

✅ **Check Kapso Status**
- Visit Kapso status page
- Check for service outages

✅ **Test API Directly**
```bash
curl -X POST https://app.kapso.ai/api/meta/messages \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "+15551234567",
    "type": "text",
    "text": {"body": "Test"}
  }'
```

---

### Issue 6: Railway Deployment Fails

**Symptoms:**
- Build fails
- App crashes on startup

**Solutions:**

✅ **Check Build Logs**
1. Railway dashboard → Deployments
2. Click failed deployment
3. Read error messages

✅ **Common Build Issues**
- Missing `requirements.txt`
- Missing `Procfile`
- Wrong Python version
- Missing files

✅ **Verify File Structure**
```
receipt-agent/
├── app.py ✓
├── whatsapp_handler.py ✓
├── claude_handler.py ✓
├── sheets_handler.py ✓
├── drive_handler.py ✓
├── credentials.json ✓
├── requirements.txt ✓
└── Procfile ✓
```

✅ **Check Environment Variables**
Ensure ALL these are set in Railway:
- KAPSO_API_KEY
- WHATSAPP_PHONE_NUMBER
- WEBHOOK_VERIFY_TOKEN
- CLAUDE_API_KEY
- GOOGLE_SHEET_ID
- GOOGLE_DRIVE_FOLDER_ID

---

### Issue 7: Duplicate Detection Not Working

**Symptoms:**
- Same receipt filed multiple times
- No duplicate warning

**Solutions:**

✅ **Check Hash Column**
- Open Google Sheet
- Verify column J (Image Hash) has values

✅ **Test Hash Function**
```python
import hashlib
with open('receipt.jpg', 'rb') as f:
    data = f.read()
    hash = hashlib.sha256(data).hexdigest()
    print(f"Hash: {hash}")
```

✅ **Clear Test Data**
- Delete test rows from Sheet
- Try again with fresh receipt

---

### Issue 8: Bot Not Asking Questions

**Symptoms:**
- Bot extracts data but doesn't ask for category/cost center
- Immediately saves without confirmation

**Solutions:**

✅ **Check Auto-Categorization**
- In `claude_handler.py`, `_auto_categorize()` may be assigning category
- If you want to always ask, modify this function

✅ **Force Questions**
```python
# In claude_handler.py, comment out auto-categorization:
# category = self._auto_categorize(extracted_data.get('merchant_name', ''))
# if category:
#     extracted_data['category'] = category
```

✅ **Check Missing Fields Logic**
```python
# In app.py, ask_for_missing_info():
required_fields = ['category', 'cost_center']  # Adjust as needed
```

---

## 🔍 Debugging Steps

### 1. Check Railway Logs
```bash
# View live logs
railway logs --follow

# Or in dashboard: Your Service → Logs tab
```

### 2. Enable Debug Mode
Add to `app.py`:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 3. Test Each Component Separately

**Test Claude:**
```python
from claude_handler import ClaudeHandler
import os

claude = ClaudeHandler(os.getenv('CLAUDE_API_KEY'))
with open('receipt.jpg', 'rb') as f:
    data = claude.extract_receipt_data(f.read())
    print(data)
```

**Test Sheets:**
```python
from sheets_handler import SheetsHandler
import os

sheets = SheetsHandler('credentials.json', os.getenv('GOOGLE_SHEET_ID'))
sheets.add_receipt({
    'merchant_name': 'Test Store',
    'date': '2024-11-25',
    'total_amount': '10.00'
})
```

**Test Drive:**
```python
from drive_handler import DriveHandler
import os

drive = DriveHandler('credentials.json', os.getenv('GOOGLE_DRIVE_FOLDER_ID'))
with open('test.jpg', 'rb') as f:
    url = drive.upload_image(f.read(), 'test.jpg')
    print(f"Uploaded: {url}")
```

---

## 📞 Getting Help

### Check These First:
1. ✅ Railway logs
2. ✅ Kapso webhook status
3. ✅ Google sharing permissions
4. ✅ API key validity
5. ✅ Environment variables

### Still Stuck?
- Railway Support: https://railway.app/help
- Kapso Support: https://app.kapso.ai/support
- Claude API: https://support.anthropic.com

---

## 🎯 Prevention Checklist

Before deploying, verify:
- [ ] Google Sheet shared with service account
- [ ] Google Drive folder shared with service account
- [ ] All env vars set in Railway
- [ ] Kapso webhook configured correctly
- [ ] Health endpoint responds
- [ ] Test receipt processes successfully
- [ ] Sheet updates with data
- [ ] Drive shows uploaded image
- [ ] Bot sends confirmation

---

## 🚀 Pro Tips

1. **Test Locally First**
   - Use ngrok for webhook testing
   - Catch errors before deploying

2. **Monitor Costs**
   - Check Claude API usage
   - Monitor Railway metrics
   - Track Kapso message counts

3. **Backup Data**
   - Export Google Sheet regularly
   - Keep receipt images

4. **Add Logging**
   - Log all API calls
   - Track processing times
   - Monitor error rates

5. **Version Control**
   - Use git for all changes
   - Tag releases
   - Document breaking changes
