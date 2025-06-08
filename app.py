import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
import time
import numpy as np
from deep_translator import GoogleTranslator
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import re
import logging
import stripe
import bcrypt
from dotenv import load_dotenv
import sqlite3
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Stripe Configuration ---
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Validate Stripe keys early
if not STRIPE_PUBLISHABLE_KEY or not stripe.api_key:
    logger.error("Stripe keys are not configured: Publishable=%s, Secret=%s",
                 STRIPE_PUBLISHABLE_KEY, stripe.api_key[:4] + "****" if stripe.api_key else None)
    raise ValueError("Stripe API keys are missing. Set STRIPE_PUBLISHABLE_KEY and STRIPE_SECRET_KEY in Streamlit Cloud Secrets.")

# --- Database Functions ---
@contextmanager
def get_db_connection():
    conn = sqlite3.connect("infibit.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT,
                email TEXT PRIMARY KEY,
                wallet_address TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("Database initialized successfully.")

def load_users():
    users = {}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            rows = cursor.fetchall()
            for row in rows:
                users[row["email"]] = {
                    "username": row["username"],
                    "wallet_address": row["wallet_address"],
                    "password_hash": row["password_hash"],
                    "created_at": row["created_at"]
                }
        return users
    except sqlite3.Error as e:
        logger.error(f"Error loading users from database: {e}")
        return {}

def save_user(email, username, wallet_address, password_hash, created_at):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (email, username, wallet_address, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (email, username, wallet_address, password_hash, created_at))
            conn.commit()
        logger.info(f"User {email} saved successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error saving user to database: {e}")
        raise

def update_wallet_address(email, wallet_address):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET wallet_address = ? WHERE email = ?", (wallet_address, email))
            conn.commit()
        logger.info(f"Wallet address updated for user {email}.")
    except sqlite3.Error as e:
        logger.error(f"Error updating wallet address: {e}")
        raise

def migrate_users_from_json():
    if os.path.exists("users.json"):
        try:
            with open("users.json", "r") as f:
                json_users = json.load(f)
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for email, data in json_users.items():
                    cursor.execute("""
                        INSERT OR IGNORE INTO users (email, username, wallet_address, password_hash, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (email, None, data["wallet_address"], data["password_hash"], data["created_at"]))
                conn.commit()
            logger.info("Migrated users from users.json to SQLite database.")
            os.rename("users.json", "users.json.bak")
        except Exception as e:
            logger.error(f"Error migrating users: {e}")

# Initialize database and migrate existing users
init_db()
migrate_users_from_json()

# --- Page Configuration ---
st.set_page_config(
    page_title="InfiBit | Bitcoin Wallet Dashboard",
    layout="wide",
    page_icon="₿",
    initial_sidebar_state="expanded",
)

# --- Language Map ---
LANGUAGE_OPTIONS = {
    "English 🇬🇧": "en",
    "French 🇫🇷": "fr",
    "German 🇩🇪": "de",
    "Spanish 🇪🇸": "es",
    "Italian 🇮🇹": "it",
    "Dutch 🇳🇱": "nl",
    "Polish 🇵🇱": "pl",
    "Portuguese 🇵🇹": "pt",
}

# --- Default Language ---
language = "en"  # Default to English

# --- Translate Function ---
def t(text):
    if language == "en":
        return text
    try:
        return GoogleTranslator(source="en", target=language).translate(text)
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text

# --- Subscription Check ---
def check_subscription(email):
    try:
        customers = stripe.Customer.list(email=email, limit=1)
        if not customers.data:
            return False
        customer = customers.data[0]
        subscriptions = stripe.Subscription.list(customer=customer.id, status="active", limit=1)
        return len(subscriptions.data) > 0
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False

# --- Password Hashing ---
def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

# --- Wallet Address Validation ---
def validate_wallet_address(address):
    pattern = r'^(bc1|[13])[a-zA-Z0-9]{25,61}$'
    return re.match(pattern, address) is not None

# --- Initialize Session State ---
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "subscribed" not in st.session_state:
    st.session_state.subscribed = False
if "wallet_address" not in st.session_state:
    st.session_state.wallet_address = ""
if "subscription_checked" not in st.session_state:
    st.session_state.subscription_checked = False

# --- Global CSS with Blur Effect ---
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body {
            background-color: #FFFFFF;
            color: #1A1A1A;
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 0;
        }
        .main {
            padding: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }
        .blur-overlay {
            filter: blur(8px);
            pointer-events: none;
            opacity: 0.6;
        }
        .paywall-container {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
            background-color: rgba(255, 255, 255, 0.9);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
            z-index: 1000;
            width: 90%;
            max-width: 500px;
        }
        .paywall-container h2 {
            font-size: 1.8em;
            margin-bottom: 20px;
        }
        .paywall-container p {
            color: #4A4A4A;
            margin-bottom: 20px;
        }
        .stMetric {
            background-color: #FFFFFF;
            border: 1px solid #E0E0E0;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            margin-bottom: 15px;
            transition: transform 0.2s;
        }
        .stMetric:hover {
            transform: translateY(-2px);
        }
        .stMetric label {
            font-size: 0.9em;
            font-weight: 600;
            color: #4A4A4A;
            margin-bottom: 5px;
            display: flex;
            align-items: center;
        }
        .stMetric .metric-value {
            font-size: 1.3em;
            font-weight: 700;
            color: #1A1A1A;
        }
        h1, h2, h3 {
            font-family: 'Inter', sans-serif;
            color: #1A1A1A;
            font-weight: 700;
        }
        h1 {
            font-size: 2.2em;
            margin-bottom: 10px;
        }
        h2 {
            font-size: 1.5em;
            margin: 20px 0 10px;
        }
        .stButton>button {
            border-radius: 6px;
            background-color: #007BFF;
            color: #FFFFFF;
            font-weight: 500;
            padding: 8px 16px;
            border: none;
            transition: background-color 0.2s;
        }
        .stButton>button:hover {
            background-color: #0056b3;
        }
        .stDataFrame table {
            border-collapse: collapse;
            width: 100%;
            font-size: 0.9em;
        }
        .stDataFrame th {
            background-color: #F5F6F5;
            color: #1A1A1A;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }
        .stDataFrame td {
            padding: 12px;
            border-bottom: 1px solid #E0E0E0;
        }
        .stDataFrame tr:nth-child(even) {
            background-color: #FAFAFA;
        }
        .stSpinner div {
            color: #007BFF;
        }
        .stTabs [data-baseweb="tab"] {
            font-size: 1em;
            font-weight: 500;
            padding: 10px 20px;
            color: #4A4A4A;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: #007BFF;
        }
        .sidebar .sidebar-content {
            background-color: #FFFFFF;
            box-shadow: 2px 0 5px rgba(0,0,0,0.05);
        }
        a {
            color: #007BFF;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        @media (max-width: 768px) {
            .main {
                padding: 10px;
            }
            .stMetric {
                padding: 10px;
            }
            h1 {
                font-size: 1.8em;
            }
            h2 {
                font-size: 1.3em;
            }
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Sidebar: Sign-Up and Login ---
with st.sidebar:
    st.markdown(
        """
        <hr style='border-color: #E0E0E0; margin: 10px 0;'>
        <h3 style='color: #1A1A1A; font-family: Inter, sans-serif;'>InfiBit Analytics</h3>
        """,
        unsafe_allow_html=True
    )
    tab_login, tab_signup = st.tabs([t("Login"), t("Sign Up")])

    # Login Tab
    with tab_login:
        email = st.text_input(t("Email"), key="login_email")
        password = st.text_input(t("Password"), type="password", key="login_password")
        if st.button(t("Login")):
            if email and password:
                users = load_users()
                user = users.get(email)
                if user and check_password(password, user["password_hash"]):
                    st.session_state.user_email = email
                    st.session_state.wallet_address = user["wallet_address"]
                    st.session_state.subscribed = check_subscription(email)
                    st.session_state.subscription_checked = True
                    st.success(t("Logged in successfully!"))
                else:
                    st.error(t("Invalid email or password."))
            else:
                st.error(t("Please enter email and password."))

    # Sign-Up Tab
    with tab_signup:
        new_username = st.text_input(t("Username (Optional)"), key="signup_username")
        new_email = st.text_input(t("Email"), key="signup_email")
        new_wallet = st.text_input(t("Bitcoin Wallet Address"), key="signup_wallet")
        new_password = st.text_input(t("Password"), type="password", key="signup_password")
        if st.button(t("Sign Up")):
            if new_email and new_wallet and new_password:
                if not validate_wallet_address(new_wallet):
                    st.error(t("Invalid Bitcoin address (must start with 'bc1', '1', or '3', 26–62 characters)."))
                else:
                    users = load_users()
                    if new_email in users:
                        st.error(t("Email already registered."))
                    else:
                        try:
                            save_user(
                                email=new_email,
                                username=new_username if new_username else None,
                                wallet_address=new_wallet,
                                password_hash=hash_password(new_password),
                                created_at=datetime.now(timezone.utc).isoformat()
                            )
                            st.success(t("Signed up successfully! Please log in."))
                        except sqlite3.Error:
                            st.error(t("Failed to register user. Please try again."))
            else:
                st.error(t("Please fill out email, wallet address, and password."))

    # Sidebar Controls (only for logged-in users)
    if st.session_state.user_email:
        if st.button(t("Logout")):
            st.session_state.user_email = None
            st.session_state.subscribed = False
            st.session_state.wallet_address = ""
            st.session_state.subscription_checked = False
            st.rerun()
        currency = st.selectbox(t("💱 Currency"), options=["USD", "GBP", "EUR"], index=0, key="currency_select")
        language_label = st.selectbox(t("🌐 Language"), options=list(LANGUAGE_OPTIONS.keys()), index=0, key="language_select")
        language = LANGUAGE_OPTIONS[language_label]
        tx_limit = st.selectbox(t("📜 Transaction Limit"), ["Last 20", "All"], index=0, help=t("Choose 'Last 20' for speed or 'All' for full history (slower for active wallets)"))

# --- Main App Logic ---
if st.session_state.user_email:
    if not st.session_state.subscribed:
        # Apply blur to main content
        st.markdown("<div class='blur-overlay'>", unsafe_allow_html=True)
        
        # Render placeholder content (blurred)
        st.markdown(
            """
            <div style='text-align: center; margin: 30px 0;'>
                <h1>Infi₿it Wallet Dashboard</h1>
                <p style='color: #4A4A4A; font-size: 1em;'>{0}</p>
            </div>
            """.format(t("Monitor your Bitcoin wallet with real-time insights")),
            unsafe_allow_html=True
        )
        with st.form("wallet_form"):
            wallet_input = st.text_input(
                t("Bitcoin Wallet Address"),
                value=st.session_state.wallet_address,
                help=t("Enter a valid Bitcoin address starting with 'bc1', '1', or '3'"),
                key="wallet_input",
                disabled=True
            )
            st.form_submit_button(t("Load Wallet Data"), disabled=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

        # Paywall overlay with Stripe Checkout
        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": "price_1RX6SQP91qk5UbUa0oV14iLB",  # Replace with your Stripe Price ID
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                success_url="https://your-app-name.streamlit.app/?subscribed=true",  # Replace with your app URL
                cancel_url="https://your-app-name.streamlit.app/?subscribed=false",
                client_reference_id=st.session_state.user_email,
            )
            st.markdown(
                f"""
                <div class='paywall-container'>
                    <h2>{t('Subscribe to InfiBit Analytics')}</h2>
                    <p>{t('Unlock full access to the Bitcoin Wallet Dashboard with our 10 day free trial!')}</p>
                    <a href="{checkout_session.url}" target="_blank">
                        <button style='background-color: #007BFF; color: #FFFFFF; padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: 500;'>
                            {t('Subscribe Now')}
                        </button>
                    </a>
                    <p style='margin-top: 20px; color: #4A4A4A; font-size: 0.9em;'>{t('After subscribing, re-login to activate your account.')}</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            logger.info(f"Stripe Checkout Session created successfully: {checkout_session.id}, URL: {checkout_session.url}")
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating checkout session: {e}")
            st.error(t("Failed to initialize payment. Please try again or contact support."))
            st.markdown(
                f"""
                <div class='paywall-container'>
                    <h2>{t('Subscribe to InfiBit Analytics')}</h2>
                    <p>{t('Unlock full access to the Bitcoin Wallet Dashboard with our 10 day free trial!')}</p>
                    <p style='color: #DC3545; font-size: 0.9em;'>{t('Payment system error. Please contact support.')}</p>
                </div>
                """,
                unsafe_allow_html=True
            )
        except Exception as e:
            logger.error(f"Unexpected error creating checkout session: {e}")
            st.error(t("Unable to load subscription system. Please try again later or contact support."))
            st.markdown(
                f"""
                <div class='paywall-container'>
                    <h2>{t('Subscribe to InfiBit Analytics')}</h2>
                    <p>{t('Unlock full access to the Bitcoin Wallet Dashboard with our 10 day free trial!')}</p>
                    <p style='color: #DC3545; font-size: 0.9em;'>{t('Subscription system is temporarily unavailable.')}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

    else:
        # Render the full app for subscribed users
        st.markdown(
            """
            <div style='text-align: center; margin: 30px 0;'>
                <h1>Infi₿it Wallet Dashboard</h1>
                <p style='color: #4A4A4A; font-size: 1em;'>{0}</p>
            </div>
            """.format(t("Monitor your Bitcoin wallet with real-time insights")),
            unsafe_allow_html=True
        )

        # Wallet address input
        with st.form("wallet_form"):
            wallet_input = st.text_input(
                t("Bitcoin Wallet Address"),
                value=st.session_state.wallet_address,
                help=t("Enter a valid Bitcoin address starting with 'bc1', '1', or '3'"),
                key="wallet_input"
            )
            submitted = st.form_submit_button(t("Load Wallet Data"))
            if submitted:
                if wallet_input and validate_wallet_address(wallet_input):
                    st.session_state.wallet_address = wallet_input
                    try:
                        update_wallet_address(st.session_state.user_email, wallet_input)
                        st.success(t("Wallet address updated successfully!"))
                    except sqlite3.Error:
                        st.error(t("Failed to update wallet address. Please try again."))
                else:
                    st.error(t("Invalid Bitcoin address (must start with 'bc1', '1', or '3', 26–62 characters)."))
                    users = load_users()
                    st.session_state.wallet_address = users.get(st.session_state.user_email, {}).get("wallet_address", "")

        # --- Constants ---
        price_cache = {}

        # --- API Functions ---
        @st.cache_data(ttl=3600)
        def get_current_btc_price():
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json().get("bitcoin", {}).get("usd", 0)
            except Exception as e:
                logger.error(f"Error fetching BTC price: {e}")
                return 0

        @st.cache_data(ttl=3600)
        def get_historical_price(date_str):
            if date_str in price_cache:
                return price_cache[date_str]
            try:
                dt = datetime.strptime(date_str, '%d-%m-%Y')
                ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
                url = f"https://min-api.cryptocompare.com/data/pricehistorical?fsym=BTC&tsyms=USD&ts={ts}"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                price = response.json().get("BTC", {}).get("USD", 0)
                price_cache[date_str] = price
                return price
            except Exception as e:
                logger.error(f"Error fetching historical price for {date_str}: {e}")
                return 0

        @st.cache_data(ttl=3600)
        def get_wallet_balance(address):
            url = f"https://blockstream.info/api/address/{address}"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                stats = response.json().get("chain_stats", {})
                funded = stats.get("funded_txo_sum", 0)
                spent = stats.get("spent_txo_sum", 0)
                balance = (funded - spent) / 1e8  # Convert satoshis to BTC
                logger.info(f"Balance for {address}: {balance:.8f} BTC")
                return max(balance, 0)
            except Exception as e:
                logger.error(f"Error fetching balance for {address}: {e}")
                st.error(t("Failed to fetch wallet balance."))
                return 0

        @st.cache_data(ttl=3600)
        def get_txs_all(address):
            all_txs = []
            url = f"https://blockstream.info/api/address/{address}/txs"
            try:
                logger.info(f"Fetching transactions for address: {address}")
                if tx_limit == "Last 20":
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    txs = response.json()
                    all_txs.extend(txs[:20])
                    logger.info(f"Fetched {len(all_txs)} transactions (limited to 20)")
                else:
                    while True:
                        response = requests.get(url, timeout=10)
                        response.raise_for_status()
                        txs = response.json()
                        if not txs:
                            break
                        all_txs.extend(txs)
                        if len(txs) < 25:
                            break
                        last_txid = txs[-1]['txid']
                        url = f"https://blockstream.info/api/address/{address}/txs/chain/{last_txid}"
                        time.sleep(1)  # Respect rate limits
                    logger.info(f"Fetched {len(all_txs)} transactions (all)")
                if not all_txs:
                    logger.warning(f"No transactions found for address: {address}")
                return all_txs
            except Exception as e:
                logger.error(f"Error fetching transactions for {address}: {e}")
                st.error(t("Failed to fetch transactions. Please try again later."))
                return []

        @st.cache_data(ttl=3600)
        def get_tx_details(txid):
            url = f"https://blockstream.info/api/tx/{txid}"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Error fetching transaction details for {txid}: {e}")
                return {}

        @st.cache_data(ttl=86400)
        def get_btc_historical_prices(days=30):
            url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                prices = response.json().get("prices", [])
                return pd.DataFrame(prices, columns=["timestamp", "price"]).assign(
                    date=lambda x: pd.to_datetime(x["timestamp"], unit="ms").dt.date
                )
            except Exception as e:
                logger.error(f"Error fetching historical BTC prices: {e}")
                return pd.DataFrame()

        @st.cache_data(ttl=900)
        def get_currency_rates():
            url = "https://api.frankfurter.app/latest?from=USD&to=USD,GBP,EUR"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                rates = data.get("rates", {})
                if "USD" not in rates:
                    rates["USD"] = 1.0
                return rates
            except Exception as e:
                logger.error(f"Error fetching currency rates: {e}")
                return {"USD": 1.0, "GBP": 0.78, "EUR": 0.92}

        # --- Stats Logic ---
        def get_wallet_stats(address):
            txs = get_txs_all(address)
            data = []
            total_btc_in = total_btc_out = total_usd_in = total_usd_out = 0
            first_tx_date = None

            for tx in txs:
                txid = tx.get("txid")
                detail = get_tx_details(txid)
                if not detail:
                    logger.warning(f"No details for txid: {txid}")
                    continue
                ts = detail.get("status", {}).get("block_time", int(time.time()))
                date = datetime.fromtimestamp(ts, tz=timezone.utc)
                date_str = date.strftime("%d-%m-%Y")
                if not first_tx_date or date < first_tx_date:
                    first_tx_date = date
                btc_price = get_historical_price(date_str)
                confirmed = detail.get("status", {}).get("confirmed", False)

                # Calculate BTC received (outputs to address)
                btc_in = sum(v.get("value", 0) for v in detail.get("vout", []) if v.get("scriptpubkey_address") == address) / 1e8
                # Calculate BTC spent (inputs from address, excluding change)
                btc_out = 0
                for vin in detail.get("vin", []):
                    prevout = vin.get("prevout", {})
                    if prevout.get("scriptpubkey_address") == address:
                        input_value = prevout.get("value", 0) / 1e8
                        change_value = sum(v.get("value", 0) for v in detail.get("vout", []) if v.get("scriptpubkey_address") == address) / 1e8
                        btc_out += max(0, input_value - change_value)
                # Counterparties
                counterparties = [vin.get("prevout", {}).get("scriptpubkey_address") for vin in detail.get("vin", []) if vin.get("prevout", {}).get("scriptpubkey_address") != address] or \
                                 [v.get("scriptpubkey_address") for v in detail.get("vout", []) if v.get("scriptpubkey_address") != address]
                counterparty = counterparties[0] if counterparties else "N/A"

                if btc_in > 0:
                    usd_in = btc_in * btc_price
                    total_btc_in += btc_in
                    total_usd_in += usd_in
                    data.append([date_str, "IN", btc_in, btc_price, usd_in, txid, confirmed, counterparty])
                if btc_out > 0:
                    usd_out = btc_out * btc_price
                    total_btc_out += btc_out
                    total_usd_out += usd_out
                    data.append([date_str, "OUT", btc_out, btc_price, usd_out, txid, confirmed, counterparty])

                logger.debug(f"Tx {txid}: IN={btc_in:.8f}, OUT={btc_out:.8f}, Price={btc_price}")

            df = pd.DataFrame(data, columns=["Date", "Type", "BTC", "Price at Tx", "USD Value", "TXID", "Confirmed", "Counterparty"])
            if not df.empty:
                df["Date"] = pd.to_datetime(df["Date"], format="%d-%m-%Y")
                df["Type"] = df["Type"].astype(str)
                df["BTC"] = df["BTC"].astype(float)
                df["Price at Tx"] = df["Price at Tx"].astype(float)
                df["USD Value"] = df["USD Value"].astype(float)
            else:
                logger.warning(f"No transaction data for address: {address}")

            return df, total_btc_in, total_btc_out, total_usd_in, total_usd_out, first_tx_date

        # --- Bit Notes Storage Functions ---
        def load_bit_notes():
            try:
                if os.path.exists("bit_notes.json"):
                    with open("bit_notes.json", "r") as f:
                        return json.load(f)
                return []
            except Exception as e:
                logger.error(f"Error loading bit notes: {e}")
                return []

        def save_bit_notes(notes):
            try:
                with open("bit_notes.json", "w") as f:
                    json.dump(notes, f, indent=4)
            except Exception as e:
                logger.error(f"Error saving bit notes: {e}")

        # --- Main Dashboard ---
        currency_rates = get_currency_rates()
        multiplier = currency_rates.get(currency.upper(), 1.0)

        if st.session_state.wallet_address:
            with st.container():
                with st.spinner(t("Loading wallet insights...")):
                    df, btc_in, btc_out, usd_in, usd_out, first_tx_date = get_wallet_stats(st.session_state.wallet_address)
                    current_price_usd = get_current_btc_price()
                    net_btc = get_wallet_balance(st.session_state.wallet_address)

                    current_price = current_price_usd * multiplier
                    net_usd = usd_in - usd_out
                    wallet_value_usd = net_btc * current_price_usd
                    wallet_value = wallet_value_usd * multiplier
                    invested = net_usd * multiplier if net_usd > 0 else wallet_value
                    gain = wallet_value - invested
                    gain_pct = (gain / invested) * 100 if invested != 0 else 0
                    avg_buy = invested / net_btc if net_btc != 0 else 0

                    if net_btc < 0:
                        logger.error(f"Negative balance detected: {net_btc:.8f} BTC")
                        st.error(t("Error: Negative balance detected. Please try fetching all transactions."))
                        net_btc = 0
                        wallet_value = 0
                        gain = 0
                        gain_pct = 0

                    holding_period_days = (datetime.now(timezone.utc) - first_tx_date).days if first_tx_date else 0
                    historical_prices = get_btc_historical_prices()
                    volatility = historical_prices["price"].pct_change().std() * np.sqrt(252) * 100 if not historical_prices.empty else 0
                    btc_return = (historical_prices["price"].iloc[-1] / historical_prices["price"].iloc[0] - 1) * 100 if not historical_prices.empty else 0
                    sharpe_ratio = (gain_pct / volatility) * np.sqrt(252) if volatility != 0 else 0
                    value_data = []
                    cost_basis = 0
                    for date in sorted(df["Date"].unique()):
                        date_df = df[df["Date"] <= date]
                        net_btc_date = date_df[date_df["Type"] == "IN"]["BTC"].sum() - date_df[date_df["Type"] == "OUT"]["BTC"].sum()
                        cost_basis += date_df[date_df["Type"] == "IN"]["USD Value"].sum() - date_df[date_df["Type"] == "OUT"]["USD Value"].sum()
                        date_str = pd.to_datetime(date).strftime("%d-%m-%Y")
                        price = get_historical_price(date_str)
                        value = net_btc_date * price * multiplier
                        value_data.append({"Date": date, "Market Value": value, "Cost Basis": cost_basis * multiplier})
                    value_df = pd.DataFrame(value_data)
                    max_drawdown = ((value_df["Market Value"] - value_df["Market Value"].cummax()) / value_df["Market Value"].cummax()).min() * 100 if not value_df.empty else 0

                    # --- Tabs ---
                    tab1, tab2, tab3, tab4 = st.tabs([t("Summary"), t("Transactions"), t("Portfolio"), t("₿it Notes")])

                    # --- Summary Tab ---
                    with tab1:
                        st.markdown(f"### 💼 {t('Wallet Overview')}")
                        if tx_limit == "Last 20":
                            st.warning(t("Showing metrics based on the last 20 transactions. For full accuracy, select 'All' transactions."))
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric(t("Bitcoin Balance"), f"{net_btc:.8f} BTC", help=t("Total Bitcoin in your wallet"))
                        col2.metric(f"{t('Current Value')} ({currency})", f"{wallet_value:,.2f}", help=t("Current market value of your Bitcoin"))
                        col3.metric(f"{t('Profit/Loss')} ({currency})", f"{gain:,.2f}", delta=f"{gain_pct:.2f}%", help=t("Unrealized profit or loss"))
                        col4.metric(t("30-Day Volatility"), f"{volatility:.2f}%", help=t("Annualized price volatility of Bitcoin"))

                        col5, col6, col7, col8 = st.columns(4)
                        col5.metric(f"{t('Average Buy Price')} ({currency})", f"{avg_buy:,.2f}", help=t("Average price paid per Bitcoin"))
                        col6.metric(f"{t('Total Invested')} ({currency})", f"{invested:,.2f}", help=t("Total amount invested"))
                        col7.metric(t("Holding Period"), f"{holding_period_days} days", help=t("Days since first transaction"))
                        col8.metric(t("Sharpe Ratio"), f"{sharpe_ratio:.2f}", help=t("Risk-adjusted return"))

                        st.markdown(f"### 📊 {t('Summary Metrics')}")
                        summary_data = {
                            t("Metric"): [
                                t("Bitcoin Balance"),
                                t("Current Value"),
                                t("Total Invested"),
                                t("Profit/Loss"),
                                t("ROI"),
                                t("Volatility"),
                                t("Sharpe Ratio")
                            ],
                            t("Value"): [
                                f"{net_btc:.8f} BTC",
                                f"{currency} {wallet_value:,.2f}",
                                f"{currency} {invested:,.2f}",
                                f"{currency} {gain:,.2f}",
                                f"{gain_pct:.2f}%",
                                f"{volatility:.2f}%",
                                f"{sharpe_ratio:.2f}"
                            ]
                        }
                        st.dataframe(pd.DataFrame(summary_data), use_container_width=True)

                    # --- Transactions Tab ---
                    with tab2:
                        st.markdown(f"### 📜 {t('Transaction History')}")
                        df_display = df.copy()
                        df_display["USD Value"] = df_display["USD Value"] * multiplier
                        df_display["Price at Tx"] = df_display["Price at Tx"] * multiplier
                        df_display["Date"] = df_display["Date"].dt.strftime("%Y-%m-%d")

                        date_range = st.date_input(
                            t("Filter by Date Range"),
                            [df["Date"].min(), df["Date"].max()],
                            min_value=df["Date"].min(),
                            max_value=df["Date"].max(),
                            key="date_range"
                        )

                        filtered_df = df_display[
                            (df_display["Date"] >= date_range[0].strftime("%Y-%m-%d")) &
                            (df_display["Date"] <= date_range[1].strftime("%Y-%m-%d"))
                        ]

                        st.dataframe(
                            filtered_df[["Date", "Type", "BTC", "USD Value", "Price at Tx", "TXID", "Confirmed", "Counterparty"]],
                            use_container_width=True
                        )

                        csv = filtered_df.to_csv(index=False)
                        st.download_button(
                            t("Download Transactions as CSV"),
                            csv,
                            "transactions.csv",
                            "text/csv",
                            key="download_transactions"
                        )

                        st.markdown(f"### 📊 {t('Transaction Volume')}")
                        volume_df = filtered_df.groupby("Date")["BTC"].sum().reset_index()
                        fig_volume = go.Figure()
                        fig_volume.add_trace(
                            go.Bar(
                                x=volume_df["Date"],
                                y=volume_df["BTC"],
                                name=t("BTC Volume"),
                                marker_color="#007BFF"
                            )
                        )
                        fig_volume.update_layout(
                            title=t("Transaction Volume Over Time"),
                            xaxis_title=t("Date"),
                            yaxis_title=t("BTC"),
                            template="plotly_white"
                        )
                        st.plotly_chart(fig_volume, use_container_width=True)

                        st.markdown(f"### 📈 {t('Transaction Frequency')}")
                        freq_df = filtered_df.groupby("Date")["TXID"].count().reset_index()
                        fig_freq = go.Figure()
                        fig_freq.add_trace(
                            go.Scatter(
                                x=freq_df["Date"],
                                y=freq_df["TXID"],
                                mode="lines+markers",
                                name=t("Transaction Count"),
                                line=dict(color="#007BFF")
                            )
                        )
                        fig_freq.update_layout(
                            title=t("Transaction Frequency Over Time"),
                            xaxis_title=t("Date"),
                            yaxis_title=t("Number of Transactions"),
                            template="plotly_white"
                        )
                        st.plotly_chart(fig_freq, use_container_width=True)

                        st.markdown(f"### 📉 {t('Transaction Statistics')}")
                        col1, col2 = st.columns(2)
                        col1.metric(t("Average BTC per Tx"), f"{filtered_df['BTC'].mean():.8f} BTC", help=t("Average BTC per transaction"))
                        col2.metric(f"{t('Average USD per Tx')} ({currency})", f"{filtered_df['USD Value'].mean():,.2f}", help=t("Average USD value per transaction"))

                    # --- Portfolio Tab ---
                    with tab3:
                        st.markdown(f"### 📈 {t('Portfolio Performance')}")
                        fig_portfolio = go.Figure()
                        fig_portfolio.add_trace(
                            go.Scatter(
                                x=value_df["Date"],
                                y=value_df["Market Value"],
                                name=t("Market Value"),
                                line=dict(color="#007BFF")
                            )
                        )
                        fig_portfolio.add_trace(
                            go.Scatter(
                                x=value_df["Date"],
                                y=value_df["Cost Basis"],
                                name=t("Cost Basis"),
                                line=dict(color="#FF5733")
                            )
                        )
                        fig_portfolio.update_layout(
                            title=t("Portfolio Value vs. Cost Basis"),
                            xaxis_title=t("Date"),
                            yaxis_title=f"{currency}",
                            template="plotly_white"
                        )
                        st.plotly_chart(fig_portfolio, use_container_width=True)

                        st.markdown(f"### 📊 {t('Performance Metrics')}")
                        col1, col2, col3 = st.columns(3)
                        col1.metric(t("ROI"), f"{gain_pct:.2f}%", help=t("Return on investment"))
                        col2.metric(f"{t('Current BTC Price')} ({currency})", f"{current_price:,.2f}", help=t("Current market price of Bitcoin"))
                        col3.metric(t("Max Drawdown"), f"{max_drawdown:.2f}%", help=t("Maximum portfolio value drop"))

                    # --- Bit Notes Tab ---
                    with tab4:
                        st.markdown(f"### 📝 {t('₿it Notes')}")
                        st.write(t("Share your thoughts on Bitcoin or track your investment notes."))

                        with st.form("bit_notes_form"):
                            st.subheader(t("Add a New Note"))
                            note_title = st.text_input(t("Note Title"), max_chars=100)
                            note_description = st.text_area(t("Description"), max_chars=500)
                            note_content = st.text_area(t("Note Content"), max_chars=1000)
                            note_submitted = st.form_submit_button(t("Submit Note"))
                            if note_submitted:
                                if note_title and note_description and note_content:
                                    notes = load_bit_notes()
                                    notes.append({
                                        "title": note_title,
                                        "description": note_description,
                                        "content": note_content,
                                        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                                        "author": st.session_state.user_email
                                    })
                                    save_bit_notes(notes)
                                    st.success(t("Note added successfully!"))
                                else:
                                    st.error(t("Please fill out all fields."))

                        st.markdown(f"### 📚 {t('Your Notes')}")
                        notes = load_bit_notes()
                        if notes:
                            for note in notes:
                                st.markdown(
                                    f"""
                                    <div style='border: 1px solid #E0E0E0; border-radius: 8px; padding: 15px; margin-bottom: 10px;'>
                                        <h4>{note['title']}</h4>
                                        <p><strong>{t('Description')}:</strong> {note['description']}</p>
                                        <p><strong>{t('Content')}:</strong> {note['content']}</p>
                                        <p><strong>{t('Date')}:</strong> {note['date']}</p>
                                        <p><strong>{t('Author')}:</strong> {note['author']}</p>
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                        else:
                            st.info(t("No notes yet. Add your first note above!"))

        else:
            st.warning(t("Please enter a Bitcoin wallet address to view insights."))

        # --- Footer ---
        st.markdown(
            """
            <div style='text-align: center; margin-top: 40px; padding: 20px; background-color: #F5F6F5; border-radius: 8px;'>
                <hr style='border-color: #E0E0E0; margin: 20px 0;'>
                <p style='color: #4A4A4A; font-size: 0.9em;'>© 2025 InfiBit Analytics. All rights reserved.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

else:
    st.markdown(
        """
        <div style='text-align: center; margin-top: 50px;'>
            <h1>Welcome to Infi₿it Analytics</h1>
            <p style='color: #4A4A4A; font-size: 1.1em;'>{0}</p>
            <p style='color: #4A4A4A;'>{1}</p>
        </div>
        """.format(
            t("Monitor your Bitcoin wallet with real-time insights"),
            t("Please sign up or log in to access the dashboard.")
        ),
        unsafe_allow_html=True
    )