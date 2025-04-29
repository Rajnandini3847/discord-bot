# Discord Expense Tracker Bot

A Discord bot that helps you track your expenses by saving them to a Google Sheet.

## Setup Instructions

1. **Create a Discord Bot**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application
   - Go to the "Bot" section and create a bot
   - Copy the bot token

2. **Set up Google Sheets API**
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project
   - Enable Google Sheets API
   - Create credentials (OAuth 2.0 Client ID)
   - Download the credentials and save as `credentials.json`
   - Create a new Google Sheet and copy its ID from the URL

3. **Environment Setup**
   - Create a `.env` file with the following content:
     ```
     DISCORD_TOKEN=your_discord_bot_token
     SPREADSHEET_ID=your_google_sheet_id
     ```

4. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the Bot**
   ```bash
   python expense_bot.py
   ```

## Usage

- `!expense <amount> <category> [description]` - Add a new expense
  Example: `!expense 25.50 food "Lunch at Subway"`
- `!help_expense` - Show available commands and categories

## Categories
- food
- transport
- entertainment
- shopping
- bills
- other 