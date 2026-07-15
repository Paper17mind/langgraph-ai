import os
import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv

def fetch_trello_emails():
    load_dotenv()
    email_user = os.getenv('EMAIL_USER')
    email_pass = os.getenv('EMAIL_PASS')
    
    if not email_user or not email_pass:
        return ["Error: EMAIL_USER or EMAIL_PASS not set in .env"]

    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(email_user, email_pass)
        mail.select('inbox')
        
        # Search for Trello emails
        status, messages = mail.search(None, '(FROM "trello")')
        email_ids = messages[0].split()

        trello_emails = []
        for e_id in email_ids[-5:]:
            status, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject_header = decode_header(msg['Subject'])[0]
                    subject = subject_header[0]
                    encoding = subject_header[1]
                    
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or 'utf-8', errors='ignore')
                    
                    date = msg.get('Date', '')
                    trello_emails.append(f"{date} - {subject}")
        mail.logout()
        return trello_emails
    except Exception as e:
        return [f"Error: {str(e)}"]

if __name__ == '__main__':
    emails = fetch_trello_emails()
    if not emails:
        print("No Trello emails found.")
    for subj in reversed(emails):
        print(f'- {subj}')
