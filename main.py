import os
import json
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ["SHEET_ID"]

service_account_info = json.loads(
os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
)

scopes = [
"https://www.googleapis.com/auth/spreadsheets",
"https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_info(
service_account_info,
scopes=scopes
)

gc = gspread.authorize(credentials)

spreadsheet = gc.open_by_key(SHEET_ID)

worksheet = spreadsheet.sheet1

worksheet.append_row([
"TEST",
"GitHub 연결 성공",
"SYSTEM",
"테스트",
"https://example.com"
])

print("Google Sheets 연결 성공")

