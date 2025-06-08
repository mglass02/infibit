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
import bcrypt
from dotenv import load_dotenv
import sqlite3
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    try:
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_email TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_email) REFERENCES users(email) ON DELETE CASCADE
                )
            """)
            conn.commit()
        logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error initializing database: {e}")
        raise

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
        logger.info(f"Loaded {len(users)} users from database.")
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

def save_note(user_email, title, description, content, created_at):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notes (user_email, title, description, content, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_email, title, description, content, created_at))
            conn.commit()
        logger.info(f"Note '{title}' saved for user {user_email}.")
    except sqlite3.Error as e:
        logger.error(f"Error saving note to database: {e}")
        raise

def load_user_notes(user_email):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notes WHERE user_email = ?", (user_email,))
            rows = cursor.fetchall()
            notes = [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "description": row["description"],
                    "content": row["content"],
                    "date": row["created_at"],
                    "author": row["user_email"]
                }
                for row in rows
            ]
        logger.info(f"Loaded {len(notes)} notes for user {user_email}.")
        return notes
    except sqlite3.Error as e:
        logger.error(f"Error loading notes for user {user_email}: {e}")
        return []

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
            logger.info(f"Migrated {len(json_users)} users from users.json to SQLite database.")
            os.rename("users.json", "users.json.bak")
        except Exception as e:
            logger.error(f"Error migrating users: {e}")

def migrate_notes_from_json():
    if os.path.exists("bit_notes.json"):
        try:
            with open("bit_notes.json", "r") as f:
                json_notes = json.load(f)
            with get_db_connection() as conn:
                cursor = conn.cursor()
                users = load_users()
                for note in json_notes:
                    user_email = note.get("author")
                    if user_email in users:
                        cursor.execute("""
                            INSERT OR IGNORE INTO notes (user_email, title, description, content, created_at)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            user_email,
                            note.get("title", "Untitled"),
                            note.get("description", ""),
                            note.get("content", note.get("contents", "")),
                            note.get("date", datetime.now(timezone.utc).isoformat())
                        ))
                conn.commit()
            logger.info(f"Migrated {len(json_notes)} notes from bit_notes.json to SQLite database.")
            os.rename("bit_notes.json", "bit_notes.json.bak")
        except Exception as e:
            logger.error(f"Error migrating notes: {e}")

# Initialize database and migrate existing data
try:
    init_db()
    migrate_users_from_json()
    migrate_notes_from_json()
except Exception as e:
    logger.error(f"Failed to initialize database or migrate data: {e}")
    st.error("Database initialization failed. Please check logs.")

# --- Page Configuration ---
st.set_page_config(
    page_title="InfiBit | Bitcoin Wallet Dashboard",
    layout="wide",
    page_icon="₿",
    initial_sidebar_state="expanded",  # Sidebar visible by default
)

# --- Language Map ---
LANGUAGE_OPTIONS = {
    "English 🇬🇧": "en",
    "French 🇫🇷": "fr",
    "German 🇩🇪": "de",
    "Spanish 🇪🇸": "es",
    "Italian 🇮🇹": "it",
    "Dutch 🇺🇱": "nl",
    "Polish 🇵🇱": "pl",
    "Portuguese 🇵🇹": "pt",
}

# --- Default Language ---
language = "en"

# --- Translate Function ---
def t(text):
    if language == "en":
        return text
    try:
        return GoogleTranslator(source="en", target=language).translate(text)
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text

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
if "wallet_address" not in st.session_state:
    st.session_state.wallet_address = ""
if "username" not in st.session_state:
    st.session_state.username = ""

# --- Global CSS ---
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@400;500;600;700&display=swap');
        body {
            background-color: #FFFFFF;
            color: #333333;
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0;
            padding: 0;
        }
        .main {
            padding: 24px;
            max-width: 1200px;
            margin: 0 auto;
        }
        .stMetric {
            background-color: #FFFFFF;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            margin-bottom: 16px;
        }
        .stMetric label {
            font-size: 0.9em;
            font-weight: 500;
            color: #666666;
            margin-bottom: 4px;
        }
        .stMetric .metric-value {
            font-size: 1.4em;
            font-weight: 600;
            color: #333333;
        }
        h1 {
            font-size: 2.4em;
            font-weight: 700;
            color: #333333;
            margin-bottom: 8px;
        }
        h2 {
            font-size: 1.6em;
            font-weight: 600;
            color: #333333;
            margin: 16px 0;
        }
        h3 {
            font-size: 1.2em;
            font-weight: 500;
            color: #333333;
        }
        .stButton>button {
            border-radius: 10px;
            background-color: #007AFF;
            color: #FFFFFF;
            font-weight: 500;
            padding: 10px 20px;
            border: none;
            transition: background-color 0.3s;
        }
        .stButton>button:hover {
            background-color: #0051D1;
        }
        .secondary-button {
            background-color: #E5E7EB;
            color: #333333;
        }
        .secondary-button:hover {
            background-color: #D1D5DB;
        }
        .stDataFrame table {
            border-collapse: collapse;
            width: 100%;
            font-size: 0.85em;
        }
        .stDataFrame th {
            background-color: #FFFFFF;
            color: #333333;
            padding: 12px;
            font-weight: 500;
            text-align: left;
            border-bottom: 1px solid #E5E7EB;
        }
        .stDataFrame td {
            padding: 12px;
            border-bottom: 1px solid #E5E7EB;
        }
        .stDataFrame tr:hover {
            background-color: #F9FAFB;
        }
        .stSpinner {
            color: #007AFF;
        }
        .stTabs [data-baseweb="tab"] {
            font-size: 1.1em;
            font-weight: 500;
            color: #666666;
            padding: 12px 24px;
            border-bottom: 2px solid transparent;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: #007AFF;
            border-bottom: 2px solid #007AFF;
        }
        .stTabs [aria-selected="true"] {
            color: #007AFF;
            border-bottom: 2px solid #007AFF;
        }
        .sidebar .sidebar-content {
            background-color: #FFFFFF;
            padding: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        .stTextInput div, .stTextInput input, .stTextInput textarea {
            border: none;
            border-radius: 8px;
            padding: 12px;
            font-size: 1.1em;
            background-color: #F5F5F7;
        }
        .stTextInput div:focus, .stTextInput input:focus, .stTextInput textarea:focus {
            background-color: #E8ECEF;
            box-shadow: none;
        }
        .stSelectbox div {
            border: none;
            border-bottom: 2px solid #CCCCCC;
            border-radius: 0;
            padding: 8px;
        }
        .card {
            background-color: #FFFFFF;
            border-radius: 14px;
            padding: 20px;
            margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        @media (max-width: 768px) {
            .main {
                padding: 16px;
            }
            h1 {
                font-size: 2em;
            }
            h2 {
                font-size: 1.4em;
            }
            .stButton>button {
                padding: 8px 16px;
            }
            .stMetric {
                padding: 12px;
            }
            .stTextInput div, .stTextInput input, .stTextInput textarea {
                font-size: 1em;
            }
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Sidebar: Sign-Up, Login, or Logout ---
with st.sidebar:
    st.markdown("<h2>InfiBit ₿</h2>", unsafe_allow_html=True)

    if not st.session_state.user_email:
        tab_login, tab_signup = st.tabs([t("Login"), t("Sign Up")])

        with tab_login:
            email = st.text_input(t("Email"), placeholder=t("Enter your email"), key="login_email")
            password = st.text_input(t("Password"), type="password", placeholder=t("Enter your password"), key="login_password")
            if st.button(t("Login"), use_container_width=True):
                if email and password:
                    users = load_users()
                    user = users.get(email)
                    if user and check_password(password, user["password_hash"]):
                        st.session_state.user_email = email
                        st.session_state.wallet_address = user["wallet_address"]
                        st.session_state.username = user["username"] or email
                        st.success(t("Logged in successfully!"), icon="✅")
                        st.rerun()
                    else:
                        st.error(t("Invalid email or password."), icon="🚨")
                else:
                    st.error(t("Please enter email and password."), icon="🚨")

        with tab_signup:
            new_username = st.text_input(t("Username (Optional)"), placeholder=t("Enter your username"), key="signup_username")
            new_email = st.text_input(t("Email"), placeholder=t("Enter your email"), key="signup_email")
            new_wallet = st.text_input(t("Bitcoin Wallet Address"), placeholder=t("Enter your wallet address"), key="signup_wallet")
            new_password = st.text_input(t("Password"), type="password", placeholder=t("Enter your password"), key="signup_password")
            if st.button(t("Sign Up"), use_container_width=True):
                if new_email and new_wallet and new_password:
                    if not validate_wallet_address(new_wallet):
                        st.error(t("Invalid Bitcoin address (must start with 'bc1', '1', or '3', 26–62 characters)."), icon="🚨")
                    else:
                        users = load_users()
                        if new_email in users:
                            st.error(t("Email already registered."), icon="🚨")
                        else:
                            try:
                                save_user(
                                    email=new_email,
                                    username=new_username if new_username else None,
                                    wallet_address=new_wallet,
                                    password_hash=hash_password(new_password),
                                    created_at=datetime.now(timezone.utc).isoformat()
                                )
                                st.success(t("Signed up successfully! Please log in."), icon="✅")
                            except sqlite3.Error as e:
                                st.error(t("Failed to register user. Please try again."), icon="🚨")
                                logger.error(f"Sign-up error: {e}")
                else:
                    st.error(t("Please fill out email, wallet address, and password."), icon="🚨")
    else:
        if st.button(t("Logout"), use_container_width=True):
            st.session_state.user_email = None
            st.session_state.wallet_address = ""
            st.session_state.username = ""
            st.rerun()
        currency = st.selectbox(t("Currency"), options=["USD", "GBP", "EUR"], index=0, key="currency_select")
        language_label = st.selectbox(t("Language"), options=list(LANGUAGE_OPTIONS.keys()), index=0, key="language_select")
        language = LANGUAGE_OPTIONS[language_label]
        tx_limit = st.selectbox(t("Transaction Limit"), ["Last 20", "All"], index=0, help=t("Choose 'Last 20' for speed or 'All' for full history"))

# --- Main App Logic ---
if st.session_state.user_email:
    st.markdown(
        """
        <div style='text-align: center; margin: 32px 0;'>
            <h1>InfiBit Dashboard</h1>
            <p style='color: #666666; font-size: 1em;'>{0}</p>
        </div>
        """.format(t("Your Bitcoin wallet at a glance")),
        unsafe_allow_html=True
    )

    # Display Username and Wallet Address
    st.markdown(
        f"""
        <div class='card'>
            <h3>{t('Account')}</h3>
            <p><strong>{t('Username')}:</strong> {st.session_state.username}</p>
            <p><strong>{t('Wallet Address')}:</strong> {st.session_state.wallet_address}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

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
            balance = (funded - spent) / 1e8
            logger.info(f"Balance for {address}: {balance:.8f} BTC")
            return max(balance, 0)
        except Exception as e:
            logger.error(f"Error fetching balance for {address}: {e}")
            st.error(t("Failed to fetch wallet balance."), icon="🚨")
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
                    time.sleep(1)
                logger.info(f"Fetched {len(all_txs)} transactions (all)")
            if not all_txs:
                logger.warning(f"No transactions found for address: {address}")
            return all_txs
        except Exception as e:
            logger.error(f"Error fetching transactions for {address}: {e}")
            st.error(t("Failed to fetch transactions."), icon="🚨")
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

            btc_in = sum(v.get("value", 0) for v in detail.get("vout", []) if v.get("scriptpubkey_address") == address) / 1e8
            btc_out = 0
            for vin in detail.get("vin", []):
                prevout = vin.get("prevout", {})
                if prevout.get("scriptpubkey_address") == address:
                    input_value = prevout.get("value", 0) / 1e8
                    change_value = sum(v.get("value", 0) for v in detail.get("vout", []) if v.get("scriptpubkey_address") == address) / 1e8
                    btc_out += max(0, input_value - change_value)
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

    # --- Main Dashboard ---
    currency_rates = get_currency_rates()
    multiplier = currency_rates.get(currency.upper(), 1.0)

    if st.session_state.wallet_address:
        with st.container():
            with st.spinner(t("Loading insights...")):
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
                    st.error(t("Negative balance detected. Try fetching all transactions."), icon="🚨")
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
                tab1, tab2, tab3, tab4 = st.tabs([f"💡 {t('Summary')}", f"📜 {t('Transactions')}", f"💰 {t('Portfolio')}", f"📝 {t('Notes')}"])

                with tab1:
                    if tx_limit == "Last 20":
                        st.warning(t("Showing last 20 transactions. Select 'All' for full accuracy."), icon="⚠️")
                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        col1, col2, col3, col4 = st.columns(4, gap="medium")
                        col1.metric(t("BTC Balance"), f"{net_btc:.8f} BTC", help=t("Current Bitcoin balance"))
                        col2.metric(t("Value"), f"{currency} {wallet_value:,.2f}", help=t("Market value"))
                        col3.metric(t("Profit/Loss"), f"{currency} {gain:,.2f}", delta=f"{gain_pct:.2f}%", help=t("Unrealized profit/loss"))
                        col4.metric(t("Volatility"), f"{volatility:.2f}%", help=t("30-day annualized volatility"))

                        col5, col6, col7, col8 = st.columns(4, gap="medium")
                        col5.metric(t("Buy Avg"), f"{currency} {avg_buy:,.2f}", help=t("Average buy price"))
                        col6.metric(t("Invested"), f"{currency} {invested:,.2f}", help=t("Total invested"))
                        col7.metric(t("Holding"), f"{holding_period_days} days", help=t("Holding period"))
                        col8.metric(t("Sharpe"), f"{sharpe_ratio:.2f}", help=t("Risk-adjusted return"))
                        st.markdown("</div>", unsafe_allow_html=True)

                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown(f"<h2>{t('Metrics')}</h2>", unsafe_allow_html=True)
                        summary_data = pd.DataFrame({
                            t("Metric"): [
                                t("BTC Balance"),
                                t("Value"),
                                t("Invested"),
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
                        })
                        st.dataframe(summary_data, use_container_width=True, hide_index=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                with tab2:
                    st.markdown(f"<h2>{t('History')}</h2>", unsafe_allow_html=True)
                    df_display = df.copy()
                    df_display["USD Value"] = df_display["USD Value"] * multiplier
                    df_display["Price at Tx"] = df_display["Price at Tx"] * multiplier
                    df_display["Date"] = df_display["Date"].dt.strftime("%Y-%m-%d")

                    date_range = st.date_input(
                        t("Date Range"),
                        [df_display["Date"].min(), df_display["Date"].max()],
                        min_value=df_display["Date"].min(),
                        max_value=df_display["Date"].max(),
                        key="date_range",
                        help=t("Select date range")
                    )

                    filtered_df = df_display[
                        (df_display["Date"] >= date_range[0].strftime("%Y-%m-%d")) &
                        (df_display["Date"] <= date_range[1].strftime("%Y-%m-%d"))
                    ]

                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.dataframe(
                            filtered_df[["Date", "Type", "BTC", "USD Value", "Price at Tx", "TXID", "Confirmed"]],
                            use_container_width=True,
                            hide_index=True,
                        )
                        st.markdown("</div>", unsafe_allow_html=True)

                    csv = filtered_df.to_csv(index=False)
                    st.download_button(
                        label=t("Download CSV"),
                        data=csv,
                        file_name="transactions.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="download_transactions"
                    )

                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown(f"<h3>{t('Volume')}</h3>", unsafe_allow_html=True)
                        volume_df = filtered_df.groupby("Date")["BTC"].sum().reset_index()
                        fig_volume = go.Figure()
                        fig_volume.add_trace(
                            go.Bar(
                                x=volume_df["Date"],
                                y=volume_df["BTC"],
                                name=t("Volume"),
                                marker_color="#007AFF"
                            )
                        )
                        fig_volume.update_layout(
                            title_text="",
                            xaxis_title="",
                            yaxis_title="BTC",
                            template="plotly_white",
                            showlegend=False,
                            margin=dict(l=0, r=0, t=0, b=0)
                        )
                        st.plotly_chart(fig_volume, use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown(f"<h3>{t('Frequency')}</h3>", unsafe_allow_html=True)
                        freq_df = filtered_df.groupby("Date")["TXID"].count().reset_index()
                        fig_freq = go.Figure()
                        fig_freq.add_trace(
                            go.Scatter(
                                x=freq_df["Date"],
                                y=freq_df["TXID"],
                                mode="lines",
                                name=t("Count"),
                                line=dict(color="#007AFF")
                            )
                        )
                        fig_freq.update_layout(
                            title_text="",
                            xaxis_title="",
                            yaxis_title="",
                            template="plotly_white",
                            showlegend=False,
                            margin=dict(l=0, r=0, t=0, b=0)
                        )
                        st.plotly_chart(fig_freq, use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown(f"<h3>{t('Statistics')}</h3>", unsafe_allow_html=True)
                        col1, col2 = st.columns(2, gap="medium")
                        col1.metric(t("Avg BTC/Tx"), f"{filtered_df['BTC'].mean():,.8f} BTC", help=t("Average BTC per transaction"))
                        col2.metric(t("Avg {currency}/Tx").format(currency=currency), f"{currency} {filtered_df['USD Value'].mean():,.2f}", help=t("Average USD per transaction"))
                        st.markdown("</div>", unsafe_allow_html=True)

                with tab3:
                    st.markdown(f"<h2>{t('Performance')}</h2>", unsafe_allow_html=True)
                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        fig_portfolio = go.Figure()
                        fig_portfolio.add_trace(
                            go.Scatter(
                                x=value_df["Date"],
                                y=value_df["Market Value"],
                                name=t("Market Value"),
                                line=dict(color="#007AFF")
                            )
                        )
                        fig_portfolio.add_trace(
                            go.Scatter(
                                x=value_df["Date"],
                                y=value_df["Cost Basis"],
                                name=t("Cost Basis"),
                                line=dict(color="#5AC8FA")
                            )
                        )
                        fig_portfolio.update_layout(
                            title_text="",
                            xaxis_title="",
                            yaxis_title=f"{currency}",
                            template="plotly_white",
                            showlegend=True,
                            legend=dict(
                                orientation="h",
                                yanchor="bottom",
                                y=1.02,
                                xanchor="right",
                                x=1
                            ),
                            margin=dict(l=0, r=20, t=20, b=0)
                        )
                        st.plotly_chart(fig_portfolio, use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown(f"<h3>{t('Metrics')}</h3>", unsafe_allow_html=True)
                        col1, col2, col3 = st.columns(3, gap="medium")
                        col1.metric(t("ROI"), f"{gain_pct:.2f}%", help=t("Return on investment"))
                        col2.metric(t("BTC Price"), f"{currency} {current_price:,.2f}", help=t("Current BTC price"))
                        col3.metric(t("Drawdown"), f"{max_drawdown:.2f}%", help=t("Maximum drawdown"))
                        st.markdown("</div>", unsafe_allow_html=True)

                with tab4:
                    st.markdown(f"<h2>{t('Notes')}</h2>", unsafe_allow_html=True)
                    with st.form("note_form", clear_on_submit=True):
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown(f"<h3>{t('New Note')}</h3>", unsafe_allow_html=True)
                        note_title = st.text_input("", placeholder=t("Note Title"), max_chars=100, key="note_title")
                        note_description = st.text_area("", placeholder=t("Description"), max_chars=500, key="note_desc")
                        note_content = st.text_area("", placeholder=t("Content"), max_chars=1000, key="note_content")
                        if st.form_submit_button(t("Add Note"), use_container_width=True):
                            if note_title and note_description and note_content:
                                try:
                                    save_note(
                                        user_email=st.session_state.user_email,
                                        title=note_title,
                                        description=note_description,
                                        content=note_content,
                                        created_at=datetime.now(timezone.utc).isoformat()
                                    )
                                    st.success(t("Note added!"), icon="✅")
                                    st.rerun()
                                except sqlite3.Error as e:
                                    st.error(t("Failed to save note."), icon="🚨")
                                    logger.error(f"Note save error: {e}")
                            else:
                                st.error(t("All fields required."), icon="🚨")
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown(f"<h3>{t('My Notes')}</h3>", unsafe_allow_html=True)
                    notes = load_user_notes(st.session_state.user_email)
                    if notes:
                        for note in notes:
                            with st.expander(f"{note['title']}", expanded=False):
                                st.markdown(
                                    f"""
                                    <div class='card'>
                                        <p><strong>{t('Description')}:</strong> {note['description']}</p>
                                        <p><strong>{t('Content')}:</strong> {note['content']}</p>
                                        <p><strong>{t('Date')}:</strong> {note['date']}</p>
                                        <p><strong>{t('Author')}:</strong> {note['author']}</p>
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                    else:
                        st.info(t("No notes yet. Add a note above."), icon="ℹ️")

    else:
        st.warning(t("No wallet address selected."), icon="⚠️")

    # --- Footer ---
    st.markdown(
        """
        <div style='text-align: center; margin-top: 64px; color: #666666; font-size: 0.9em;'>
            © 2025 InfiBit. All rights reserved.
        </div>
        """,
        unsafe_allow_html=True
    )

else:
    st.markdown(
        """
        <div style='text-align: center; margin: 64px 0;'>
            <h1>InfiBit Analytics</h1>
            <p style='color: #666666; font-size: 1.1em;'>{0}</p>
        </div>
        """.format(t("Track your Bitcoin with ease")),
        unsafe_allow_html=True
    )