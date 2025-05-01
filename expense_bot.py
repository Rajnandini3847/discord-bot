import os
import discord
from discord.ext import commands
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pickle
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

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
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
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

        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range='Expenses!A1:D1').execute()
        if not sheet.get('values'):
            headers = [["Timestamp", "Amount", "Category", "Description"]]
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID, range='Expenses!A1:D1', valueInputOption='RAW', body={"values": headers}
            ).execute()

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        values = [[timestamp, amount, category, description]]
        body = {'values': values}

        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
            valueInputOption='RAW', insertDataOption='INSERT_ROWS', body=body
        ).execute()

        await ctx.send(f'✅ Expense added!\nAmount: ₹{amount}\nCategory: {category}\nDescription: {description}')
    except Exception as e:
        await ctx.send(f'❌ Error: {str(e)}')

def filter_rows_by_time(rows, time_range):
    now = datetime.now()
    if time_range == 'day':
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif time_range == 'week':
        cutoff = now - timedelta(days=7)
    elif time_range == 'month':
        cutoff = now - timedelta(days=30)
    else:
        return rows

    filtered = []
    for row in rows[1:]:
        try:
            ts = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
            if ts >= cutoff:
                filtered.append(row)
        except:
            continue
    return filtered

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

def is_date_in_range(date_str, range_type):
    try:
        entry_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return False

    now = datetime.now()

    if range_type == 'day':
        return entry_date.date() == now.date()
    elif range_type == 'week':
        return (now - entry_date).days < 7
    elif range_type == 'month':
        return entry_date.year == now.year and entry_date.month == now.month
    return False

async def send_summary(ctx, range_type):
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
            if len(row) < 3:
                continue
            timestamp, amount, category = row[0], row[1], row[2]
            if is_date_in_range(timestamp, range_type):
                try:
                    summary[category.strip().lower()] += float(amount)
                except:
                    continue

        if not summary:
            await ctx.send(f"No expenses found for this {range_type}.")
            return

        message = f"**📅 Expense Summary for This {range_type.capitalize()}**\n"
        for category, total in summary.items():
            message += f"**{category.capitalize()}**: ₹{total:.2f}\n"

        await ctx.send(message)

    except Exception as e:
        await ctx.send(f"❌ Error fetching {range_type} summary: {str(e)}")


@bot.command(name='summary_day')
async def summary_day(ctx):
    await send_summary(ctx, "day")

@bot.command(name='summary_week')
async def summary_week(ctx):
    await send_summary(ctx, "week")

@bot.command(name='summary_month')
async def summary_month(ctx):
    await send_summary(ctx, "month")

@bot.command(name='total')
async def total_expense(ctx):
    try:
        service = get_google_sheets_service()
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        rows = result.get('values', [])[1:]
        total = sum(float(row[1]) for row in rows if len(row) > 1)
        await ctx.send(f"💰 Total spent: ₹{total:.2f}")
    except:
        await ctx.send("❌ Failed to calculate total.")

@bot.command(name='top_categories')
async def top_categories(ctx):
    try:
        service = get_google_sheets_service()
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        rows = result.get('values', [])[1:]

        summary = defaultdict(float)
        for row in rows:
            try:
                summary[row[2].strip().lower()] += float(row[1])
            except:
                continue

        top = sorted(summary.items(), key=lambda x: x[1], reverse=True)[:3]
        if not top:
            await ctx.send("No categories found.")
            return

        message = "**🔥 Top 3 Categories:**\n"
        for cat, amt in top:
            message += f"**{cat.capitalize()}**: ₹{amt:.2f}\n"
        await ctx.send(message)

    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='delete_last')
async def delete_last(ctx):
    try:
        service = get_google_sheets_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        rows = sheet.get('values', [])

        if len(rows) <= 1:
            await ctx.send("Nothing to delete.")
            return

        last_row_index = len(rows)
        service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID, range=f'Expenses!A{last_row_index}:D{last_row_index}'
        ).execute()

        await ctx.send("🗑️ Last expense deleted.")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='most_expensive')
async def most_expensive(ctx):
    try:
        service = get_google_sheets_service()
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        rows = result.get('values', [])[1:]

        max_row = max(rows, key=lambda x: float(x[1]) if len(x) > 1 else 0, default=None)

        if not max_row:
            await ctx.send("No data available.")
            return

        await ctx.send(f"💸 Most expensive: ₹{max_row[1]} for **{max_row[2]}** - {max_row[3]}")
    except:
        await ctx.send("❌ Failed to fetch most expensive expense.")

@bot.command(name='help_expense')
async def help_expense(ctx):
    help_text = """
**📘 Expense Bot Commands:**
`!expense <amount> <category> [description]` – Add a new expense  

`!summary` - Total expenses by category  
`!summary_day` - Expenses for today  
`!summary_week` - Expenses for last 7 days  
`!summary_month` - Expenses for this month

`!total` – Show total spent  
`!top_categories` – Show top 3 categories  
`!delete_last` – Delete the most recent expense  
`!most_expensive` – Show most expensive entry  
`!help_expense` – Show this help

**Categories examples:** food, travel, shopping, etc.
    """
    await ctx.send(help_text)

bot.run(os.getenv('DISCORD_TOKEN'))
