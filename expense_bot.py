
import os
import discord
from discord.ext import commands
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
from collections import defaultdict
import asyncio
import threading
import webbrowser

# Load env vars
load_dotenv()

# Discord setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Constants
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDENTIALS_FILE = 'credentials.json'
TOKENS_DIR = 'tokens'
REDIRECT_URI = 'http://localhost:8080'  # Local redirect URI
if not os.path.exists(TOKENS_DIR):
    os.makedirs(TOKENS_DIR)

# Store auth flows for users
user_flows = {}

# Bot events
@bot.event
async def on_ready():
    print(f'{bot.user} is live!')

# Get user creds
def get_user_credentials(user_id):
    token_path = os.path.join(TOKENS_DIR, f"{user_id}.json")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        else:
            return None
    return creds

# Google Sheets API build
def get_sheets_service(creds):
    return build('sheets', 'v4', credentials=creds)

# Command: Connect - using local server flow
@bot.command(name='connect')
async def connect(ctx):
    user_id = str(ctx.author.id)
    
    # Create a flow for this user
    flow = InstalledAppFlow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # Store the flow for this user
    user_flows[user_id] = flow
    
    # Create a message with instructions
    auth_url = flow.authorization_url()[0]
    
    # Send the auth URL to the user
    await ctx.send(f"🔗 Please authorize access by clicking this link: {auth_url}\n"
                   f"After authorization, you'll be redirected to a local webpage. "
                   f"The authentication will complete automatically.")
    
    # Start a local server in a separate thread to handle the OAuth callback
    threading.Thread(target=run_auth_server, args=(user_id, ctx)).start()

def run_auth_server(user_id, ctx):
    """Run the authorization server in a separate thread."""
    flow = user_flows.get(user_id)
    if not flow:
        return
    
    # Run the local server to get the authorization response
    creds = flow.run_local_server(port=8080)
    
    # Save the credentials
    with open(os.path.join(TOKENS_DIR, f"{user_id}.json"), 'w') as token:
        token.write(creds.to_json())
    
    # Schedule a message to be sent in Discord
    asyncio.run_coroutine_threadsafe(
        ctx.send("✅ Successfully connected your Google account!"), 
        bot.loop
    )
    
    # Clean up
    if user_id in user_flows:
        del user_flows[user_id]

@bot.command(name='sheets_info')
async def sheets_info(ctx):
    """Shows information about user's sheets and the spreadsheet URL"""
    user_id = str(ctx.author.id)
    creds = get_user_credentials(user_id)
    if not creds:
        await ctx.send("❌ You're not connected. Use `!connect`.")
        return
        
    sheet_service = get_sheets_service(creds)
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    
    try:
        # Get spreadsheet information
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        spreadsheet_title = spreadsheet.get('properties', {}).get('title', 'Untitled Spreadsheet')
        sheets = spreadsheet.get('sheets', [])
        
        user_sheet_name = f"User_{user_id}"
        user_sheet_found = False
        
        for sheet in sheets:
            if sheet['properties']['title'] == user_sheet_name:
                user_sheet_found = True
                sheet_id = sheet['properties']['sheetId']
                break
        
        # Get spreadsheet URL
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        sheet_url = f"{spreadsheet_url}#gid={sheet_id}" if user_sheet_found else spreadsheet_url
        
        if user_sheet_found:
            await ctx.send(f"**📊 Your Expense Sheet Info**\n"
                         f"**Spreadsheet**: {spreadsheet_title}\n"
                         f"**Your Sheet**: {user_sheet_name}\n"
                         f"**Link**: {sheet_url}")
        else:
            await ctx.send(f"**📊 Expense Spreadsheet Info**\n"
                         f"**Spreadsheet**: {spreadsheet_title}\n"
                         f"You don't have a sheet yet. Add an expense to create one.\n"
                         f"**Link**: {spreadsheet_url}")
    
    except Exception as e:
        await ctx.send(f"❌ Error retrieving sheet info: {str(e)}")

# Command: Add expense
@bot.command(name='expense')
async def add_expense(ctx, amount: float, category: str, *, description: str = ""):
    user_id = str(ctx.author.id)
    creds = get_user_credentials(user_id)
    if not creds:
        await ctx.send("❌ You're not connected. Use `!connect`.")
        return

    sheet_service = get_sheets_service(creds)
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    sheet_name = f"User_{user_id}"  # Prefix with "User_" to make it a valid sheet name
    
    # First, check if the sheet exists, if not create it
    try:
        # Get all sheet metadata
        sheet_metadata = sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', '')
        
        # Check if user's sheet exists
        sheet_exists = False
        for sheet in sheets:
            if sheet['properties']['title'] == sheet_name:
                sheet_exists = True
                break
                
        # If sheet doesn't exist, create it with headers
        if not sheet_exists:
            # Create new sheet
            request = {
                'addSheet': {
                    'properties': {
                        'title': sheet_name
                    }
                }
            }
            sheet_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': [request]}
            ).execute()
            
            # Add headers
            headers = [['Timestamp', 'Amount', 'Category', 'Description']]
            sheet_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f'{sheet_name}!A1:D1',
                valueInputOption='RAW',
                body={'values': headers}
            ).execute()
            
            # Get spreadsheet URL
            spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid="
            await ctx.send(f"✅ Created new expense sheet named '{sheet_name}'. You can view your expenses at: {spreadsheet_url}")
        
        # Now add the expense
        range_name = f'{sheet_name}!A:D'
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        values = [[timestamp, amount, category, description]]

        sheet_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body={'values': values}
        ).execute()
        
        await ctx.send(f'✅ Expense added: ₹{amount} for {category}')
        
    except Exception as e:
        await ctx.send(f'❌ Error: {str(e)}')

        await ctx.send(f'✅ Expense added: ₹{amount} for {category}')
    except Exception as e:
        await ctx.send(f'Error: {str(e)}')

# Summary Helper
async def send_summary(ctx, days=0):
    user_id = str(ctx.author.id)
    creds = get_user_credentials(user_id)
    if not creds:
        await ctx.send("❌ Use `!connect` to link your account.")
        return

    service = get_sheets_service(creds)
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    sheet_name = f"User_{user_id}"  # Prefix with "User_" to make it a valid sheet name
    range_name = f'{sheet_name}!A:D'

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()

        rows = result.get('values', [])
        if len(rows) <= 1:  # Check if there's only a header or no data
            await ctx.send("No expenses found.")
            return
            
        rows = rows[1:]  # skip header
        summary = defaultdict(float)

        for row in rows:
            try:
                if len(row) >= 3:  # Make sure we have enough columns
                    timestamp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                    if days:
                        if timestamp < datetime.now() - timedelta(days=days):
                            continue
                    amount = float(row[1])
                    category = row[2].lower()
                    summary[category] += amount
            except Exception as e:
                continue

        if not summary:
            await ctx.send("No expenses found.")
            return

        message = f"**📊 Summary (Last {days} days)**\n" if days else "**📊 Total Summary**\n"
        for cat, total in sorted(summary.items(), key=lambda x: x[1], reverse=True):
            message += f"**{cat.capitalize()}**: ₹{total:.2f}\n"
        await ctx.send(message)

    except Exception as e:
        await ctx.send(f'❌ Error fetching summary: {str(e)}')

@bot.command(name='summary')
async def summary(ctx):
    await send_summary(ctx, days=0)

@bot.command(name='summary_day')
async def summary_day(ctx):
    await send_summary(ctx, days=1)

@bot.command(name='summary_week')
async def summary_week(ctx):
    await send_summary(ctx, days=7)

@bot.command(name='summary_month')
async def summary_month(ctx):
    await send_summary(ctx, days=30)

@bot.command(name='top_categories')
async def top_categories(ctx):
    user_id = str(ctx.author.id)
    creds = get_user_credentials(user_id)
    if not creds:
        await ctx.send("❌ Use `!connect` to link your account.")
        return

    service = get_sheets_service(creds)
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    sheet_name = f"User_{user_id}"  # Prefix with "User_" to make it a valid sheet name
    range_name = f'{sheet_name}!A:D'

    try:
        result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        rows = result.get('values', [])
        
        if len(rows) <= 1:
            await ctx.send("No expenses found.")
            return
            
        rows = rows[1:]  # Skip header
        summary = defaultdict(float)

        for row in rows:
            try:
                if len(row) >= 3:
                    category = row[2].lower()
                    amount = float(row[1])
                    summary[category] += amount
            except:
                continue

        top3 = sorted(summary.items(), key=lambda x: x[1], reverse=True)[:3]
        if not top3:
            await ctx.send("No expenses found.")
            return

        message = "**🔥 Top 3 Categories:**\n"
        for cat, total in top3:
            message += f"**{cat.capitalize()}**: ₹{total:.2f}\n"
        await ctx.send(message)

    except Exception as e:
        await ctx.send(f'❌ Error: {str(e)}')

@bot.command(name='delete_last')
async def delete_last(ctx):
    user_id = str(ctx.author.id)
    creds = get_user_credentials(user_id)
    if not creds:
        await ctx.send("❌ Use `!connect` to link your account.")
        return

    service = get_sheets_service(creds)
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    sheet_name = f"User_{user_id}"  # Prefix with "User_" to make it a valid sheet name
    range_name = f'{sheet_name}!A:D'

    try:
        sheet_metadata = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        rows = sheet_metadata.get('values', [])

        if len(rows) <= 1:
            await ctx.send("❌ No expenses to delete.")
            return

        last_index = len(rows)
        delete_range = f"{sheet_name}!A{last_index}:D{last_index}"
        service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=delete_range, body={}).execute()
        await ctx.send("🗑️ Last expense deleted.")

    except Exception as e:
        await ctx.send(f'❌ Error: {str(e)}')

@bot.command(name='most_expensive')
async def most_expensive(ctx):
    user_id = str(ctx.author.id)
    creds = get_user_credentials(user_id)
    if not creds:
        await ctx.send("❌ Use `!connect` to link your account.")
        return

    service = get_sheets_service(creds)
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    sheet_name = f"User_{user_id}"  # Prefix with "User_" to make it a valid sheet name
    range_name = f'{sheet_name}!A:D'

    try:
        result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        rows = result.get('values', [])
        
        if len(rows) <= 1:
            await ctx.send("No expenses found.")
            return
            
        rows = rows[1:]  # Skip header

        if not rows:
            await ctx.send("No expenses found.")
            return

        valid_rows = [row for row in rows if len(row) > 1 and row[1].replace('.', '', 1).isdigit()]
        if not valid_rows:
            await ctx.send("No valid expenses found.")
            return
            
        max_row = max(valid_rows, key=lambda row: float(row[1]))
        
        description = max_row[3] if len(max_row) > 3 else "No description"
        message = f"💸 **Most Expensive:** ₹{max_row[1]} for **{max_row[2]}** — {description} on {max_row[0]}"
        await ctx.send(message)

    except Exception as e:
        await ctx.send(f'❌ Error: {str(e)}')

# Help
@bot.command(name='help_expense')
async def help_expense(ctx):
    await ctx.send("""
**💰 Expense Bot Commands:**
`!connect` - Link your Google account (click the link to authorize)
`!expense <amount> <category> <description>` - Add an expense
`!summary` - Get full summary of all expenses
`!summary_day` - Summary for today only
`!summary_week` - Last 7 days summary
`!summary_month` - Last 30 days summary
`!top_categories` - Top 3 spending categories
`!delete_last` - Delete your last recorded expense
`!most_expensive` - Show your highest expense entry
`!sheets_info` - Show information about your spreadsheet and link
    """)

bot.run(os.getenv("DISCORD_TOKEN"))