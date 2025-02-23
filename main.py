from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = FastAPI()

app_password = "nhna jzdm cdna uydo"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

class EmailRequest(BaseModel):
    recipient: EmailStr
    subject: str
    message: str

@app.get("/wayback/")
async def wayback_proxy(url: str):
    try:
        wayback_url = f"https://web.archive.org/web/timemap/json?url={url}&matchType=prefix&collapse=urlkey&output=json&fl=original,mimetype,timestamp,endtimestamp,groupcount,uniqcount&filter=!statuscode:[45]..&limit=50000"
        response = requests.get(wayback_url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

@app.post("/send-email")
def send_email(email_request: EmailRequest):
    sender_email = "iconicwwebsite@gmail.com"
    
    # Create the email message
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = email_request.recipient
    msg["Subject"] = email_request.subject

    msg["X-Priority"] = "2"
    msg["Priority"] = "Urgent"
    msg["Importance"] = "High"

    msg.attach(MIMEText(email_request.message, "plain"))
    
    try:
        # Connect to Gmail's SMTP server
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()  # Secure the connection
        server.login(sender_email, app_password)
        # Send the email
        server.sendmail(sender_email, email_request.recipient, msg.as_string())
        server.quit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email not sent: {str(e)}")
    
    return {"message": "Email sent successfully"}