import imaplib
import email
import os
from langchain.tools import tool

@tool
def search_email(search_query: str, limit: int = 5) -> str:
    """
    Search emails using IMAP search syntax.
    Example search_query: '(SINCE "01-Jun-2026" BEFORE "01-Jul-2026" SUBJECT "Top Up")'
    Returns parsed subjects, dates, and body text snippets.
    """
    user = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASS")
    
    if not user or not password:
        return "EMAIL_USER or EMAIL_PASS not set."

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select("inbox")
        
        status, messages = mail.search(None, search_query)
        if status != "OK":
            return f"Search failed: {status}"
            
        email_ids = messages[0].split()
        if not email_ids:
            return "No emails found."
            
        email_ids = email_ids[-limit:]
        
        results = []
        for e_id in email_ids:
            status, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    date_str = msg.get("Date")
                    subject = email.header.decode_header(msg.get("Subject"))[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(errors='ignore')
                    
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() in ["text/plain", "text/html"]:
                                body += part.get_payload(decode=True).decode(errors='ignore')
                    else:
                        body = msg.get_payload(decode=True).decode(errors='ignore')
                    
                    results.append(f"Date: {date_str}\nSubject: {subject}\nBody Snippet:\n{body[:500]}")
                    
        mail.logout()
        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Error: {str(e)}"
