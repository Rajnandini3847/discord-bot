import os
import discord
from discord.ext import commands
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime
import json
import pickle
from dotenv import load_dotenv
from collections import defaultdict

# Load environment variables
load_dotenv()

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
RANGE_NAME = 'Expenses!A:D'

def get_google_sheets_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('sheets', 'v4', credentials=creds)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.command(name='expense')
async def add_expense(ctx, amount: float, category: str, *, description: str = ""):
    try:
        service = get_google_sheets_service()

        sheet = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range='Expenses!A1:D1'
        ).execute()
        if not sheet.get('values'):
            headers = [["Timestamp", "Amount", "Category", "Description"]]
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range='Expenses!A1:D1',
                valueInputOption='RAW',
                body={"values": headers}
            ).execute()

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        values = [[timestamp, amount, category, description]]

        body = {
            'values': values
        }

        # Append the data to the sheet
        result = service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()

        await ctx.send(f'✅ Expense added successfully!\nAmount: ₹{amount}\nCategory: {category}\nDescription: {description}')

    except Exception as e:
        await ctx.send(f'Error adding expense: {str(e)}')

@bot.command(name='summary')
async def expense_summary(ctx):
    try:
        service = get_google_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME
        ).execute()

        rows = result.get('values', [])
        if len(rows) <= 1:
            await ctx.send("No expense data available.")
            return

        summary = defaultdict(float)
        for row in rows[1:]:
            try:
                amount = float(row[1])
                category = row[2].strip().lower() if len(row) > 2 else "uncategorized"
                summary[category] += amount
            except:
                continue

        if not summary:
            await ctx.send("No expenses found.")
            return

        message = "**📊 Expense Summary:**\n"
        for category, total in summary.items():
            message += f"**{category.capitalize()}**: ₹{total:.2f}\n"

        await ctx.send(message)

    except Exception as e:
        await ctx.send(f"❌ Error fetching summary: {str(e)}")

@bot.command(name='help_expense')
async def help_expense(ctx):
    help_text = """
**Expense Bot Commands:**
`!expense <amount> <category> [description]` - Add a new expense  
Example: `!expense 250 food "Lunch"`

`!summary` - Get category-wise total summary of expenses

**Categories:**
- food
- transport
- entertainment
- shopping
- bills
- other
    """
    await ctx.send(help_text)

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))
