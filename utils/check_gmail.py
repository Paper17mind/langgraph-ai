import os
import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv

def fetch_unread_emails():
    load_dotenv()
    email_user = os.getenv('EMAIL_USER')
    email_pass = os.getenv('EMAIL_PASS')
    
    if not email_user or not email_pass:
        return ["Error: EMAIL_USER or EMAIL_PASS not set in .env"]

    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(email_user, email_pass)
        mail.select('inbox')
        
        status, messages = mail.search(None, 'UNSEEN')
        unread_ids = messages[0].split()

        unread_emails = []
        for e_id in unread_ids[-5:]:  # Limit 5
            status, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject_header = decode_header(msg['Subject'])[0]
                    subject = subject_header[0]
                    encoding = subject_header[1]
                    
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or 'utf-8', errors='ignore')
                    
                    unread_emails.append(subject)
        mail.logout()
        return unread_emails
    except Exception as e:
        return [f"Error: {str(e)}"]

if __name__ == '__main__':
    emails = fetch_unread_emails()
    for subj in emails:
        print(f'- {subj}')