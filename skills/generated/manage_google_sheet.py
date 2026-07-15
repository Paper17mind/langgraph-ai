import os
import json
import gspread
from google.oauth2.service_account import Credentials

@tool
def manage_google_sheet(spreadsheet_id: str, action: str, worksheet_name: str = "Sheet1", cell_range: str = None, values: list = None) -> str:
    """
    Akses dan modifikasi Google Sheets.
    
    Args:
        spreadsheet_id (str): ID dari URL Google Sheet.
        action (str): "read", "update", atau "append".
        worksheet_name (str): Nama tab sheet (default: Sheet1).
        cell_range (str, optional): Rentang sel, misal "A1:C10".
        values (list, optional): List of lists untuk update/append. Misal [["A", "B"]].
    """
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path or not os.path.exists(cred_path):
        return f"Error: Kredensial tidak ditemukan di {cred_path}. Set GOOGLE_APPLICATION_CREDENTIALS di .env."

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        creds = Credentials.from_service_account_file(cred_path, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        
        if action == "read":
            data = sheet.get(cell_range) if cell_range else sheet.get_all_values()
            return json.dumps(data)
            
        elif action == "update":
            if not cell_range or not values:
                return "Error: 'update' butuh 'cell_range' dan 'values'."
            sheet.update(cell_range, values)
            return f"Update sukses di {cell_range}."
            
        elif action == "append":
            if not values:
                return "Error: 'append' butuh 'values'."
            sheet.append_rows(values)
            return f"Append {len(values)} baris sukses."
            
        else:
            return f"Error: Action '{action}' tidak valid."
            
    except Exception as e:
        return f"Error eksekusi: {str(e)}"
