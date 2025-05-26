from Navigation_Bot.googleSheetsManager import GoogleSheetsManager

sheets_manager = GoogleSheetsManager()

INPUT_FILEPATH = "config/selected_data.json"
sheets_manager.refresh_name(sheets_manager.load_data(), INPUT_FILEPATH)
