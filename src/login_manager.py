import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Set up logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

try:
    from src.core.config_loader import ConfigLoader, CONFIG_DIR, DEFAULT_ACCOUNTS_FILE
    from src.core.browser_manager.service import BrowserManager
    from src.utils.login_state import wait_for_signed_in
except ImportError:
    # If running directly from src/
    sys.path.append(str(PROJECT_ROOT / 'src'))
    from core.config_loader import ConfigLoader, CONFIG_DIR, DEFAULT_ACCOUNTS_FILE
    from core.browser_manager.service import BrowserManager
    from utils.login_state import wait_for_signed_in

def load_accounts(config_loader: ConfigLoader) -> List[Dict[str, Any]]:
    return config_loader.get_accounts_config()

def save_cookies(filepath: Path, cookies: List[Dict[str, Any]]) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open('w', encoding='utf-8') as f:
        json.dump(cookies, f, indent=4)
    logger.info(f"Cookies saved to {filepath}")

def update_account_config(accounts_file: Path, account_id: str, cookie_path: str) -> None:
    try:
        with accounts_file.open('r', encoding='utf-8') as f:
            accounts = json.load(f)

        updated = False
        for account in accounts:
            if account.get('account_id') == account_id:
                account['cookie_file_path'] = cookie_path
                updated = True
                break

        if updated:
            with accounts_file.open('w', encoding='utf-8') as f:
                json.dump(accounts, f, indent=4)
            logger.info(f"Updated account configuration for {account_id}")
        else:
            logger.warning(f"Account {account_id} not found in {accounts_file}")

    except Exception as e:
        logger.error(f"Failed to update accounts file: {e}")

def main():
    print("Twitter Login Manager")
    print("=====================")

    config_loader = ConfigLoader()
    accounts = load_accounts(config_loader)

    if not accounts:
        logger.error("No accounts found in config/accounts.json")
        return

    print("\nAvailable Accounts:")
    for idx, account in enumerate(accounts):
        print(f"{idx + 1}. {account.get('account_id', 'Unknown ID')} (Active: {account.get('is_active', False)})")

    while True:
        try:
            choice = input("\nSelect account number (or 'q' to quit): ").strip()
            if choice.lower() == 'q':
                return
            idx = int(choice) - 1
            if 0 <= idx < len(accounts):
                selected_account = accounts[idx]
                break
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a number.")

    account_id = selected_account.get('account_id')
    logger.info(f"Selected account: {account_id}")

    # Determine cookie file path
    current_cookie_path = selected_account.get('cookie_file_path')
    if not current_cookie_path:
        default_path = f"data/cookies/{account_id}.json"
        print(f"\nNo cookie file path configured for this account.")
        use_default = input(f"Use default path '{default_path}'? (Y/n): ").strip().lower()
        if use_default in ('', 'y', 'yes'):
            target_cookie_path = default_path
        else:
            target_cookie_path = input("Enter path to save cookies (relative to project root): ").strip()
    else:
        target_cookie_path = current_cookie_path
        print(f"\nUsing existing cookie file path: {target_cookie_path}")

    # Ask to clear existing cookies
    clear_cookies = input("Clear existing cookies before login? (y/N): ").strip().lower()
    start_fresh = clear_cookies in ('y', 'yes')

    # Prepare browser configuration
    # Force headless to False for manual interaction
    # ConfigLoader loads settings into self.settings
    # We modify it in memory for this session
    original_headless = config_loader.settings.get('browser_settings', {}).get('headless', False)
    if 'browser_settings' not in config_loader.settings:
        config_loader.settings['browser_settings'] = {}
    config_loader.settings['browser_settings']['headless'] = False

    # Prepare account config for BrowserManager
    # If starting fresh, we don't pass cookie info to BrowserManager so it doesn't load them
    bm_account_config = selected_account.copy()
    if start_fresh:
        bm_account_config.pop('cookies', None)
        bm_account_config.pop('cookie_file_path', None)

    logger.info("Launching browser... Please log in manually.")

    try:
        with BrowserManager(account_config=bm_account_config, config_loader=config_loader) as browser:
            driver = browser.get_driver()

            # Navigate to login page
            login_url = "https://x.com/login"
            browser.navigate_to(login_url)

            print("\nBrowser launched. Please log in to Twitter in the opened window.")
            print("Once you are logged in and on the home page, press Enter here.")
            input("Press Enter to save cookies...")

            # Optional: Check if actually logged in
            if wait_for_signed_in(driver, max_wait_seconds=5):
                logger.info("Detected logged in state.")
            else:
                logger.warning("Could not automatically detect logged in state. Proceeding to save cookies anyway.")

            # Get cookies
            cookies = driver.get_cookies()
            logger.info(f"Captured {len(cookies)} cookies.")

            # Save cookies
            full_cookie_path = PROJECT_ROOT / target_cookie_path
            save_cookies(full_cookie_path, cookies)

            # Update account config if path changed
            if current_cookie_path != target_cookie_path:
                update_account_config(DEFAULT_ACCOUNTS_FILE, account_id, target_cookie_path)
                print(f"Updated account config with new cookie path: {target_cookie_path}")

            print("\nLogin successful and cookies saved!")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        # Restore original setting (though process is ending)
        config_loader.settings['browser_settings']['headless'] = original_headless

if __name__ == "__main__":
    main()
