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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body {
            background-color: #FFFFFF;
            color: #1A1A1A;
            font-family: 'Inter', sans-serif;
            font-size: 0.95em;
            line-height: 1.5;
            margin: 0;
            padding: 0;
        }
        .main {
            padding: 24px;
            max-width: 1400px;
            margin: 0 auto;
        }
        .stMetric {
            background-color: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            margin-bottom: 16px;
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
        h1 {
            font-size: 2.4em;
            font-weight: 700;
            color: #1A1A1A;
            margin-bottom: 12px;
        }
        h2 {
            font-size: 1.7em;
            font-weight: 600;
            color: #1A1A1A;
            margin: 24px 0 12px;
        }
        h3 {
            font-size: 1.3em;
            font-weight: 600;
            color: #1A1A1A;
            margin: 16px 0 8px;
        }
        .stButton>button {
            border-radius: 6px;
            background-color: #007BFF;
            color: #FFFFFF;
            font-weight: 500;
            padding: 10px 20px;
            border: none;
            transition: background-color 0.2s;
        }
        .stButton>button:hover {
            background-color: #0056b3;
        }
        .secondary-button>button {
            background-color: #6B7280;
            color: #FFFFFF;
        }
        .secondary-button>button:hover {
            background-color: #4B5563;
        }
        .stDataFrame table {
            border-collapse: collapse;
            width: 100%;
            font-size: 0.9em;
        }
        .stDataFrame th {
            background-color: #F5F6F5;
            color: #1A1A1A;
            padding: 14px;
            text-align: left;
            font-weight: 600;
            border-bottom: 1px solid #E5E7EB;
        }
        .stDataFrame td {
            padding: 14px;
            border-bottom: 1px solid #E5E7EB;
        }
        .stDataFrame tr:nth-child(even) {
            background-color: #FAFAFA;
        }
        .stDataFrame tr:hover {
            background-color: #F1F5F9;
        }
        .stSpinner div {
            color: #007BFF;
        }
        .stTabs [data-baseweb="tab"] {
            font-size: 1.1em;
            font-weight: 500;
            padding: 12px 24px;
            color: #4A4A4A;
            border-bottom: 2px solid transparent;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: #007BFF;
            border-bottom: 2px solid #007BFF;
        }
        .stTabs [aria-selected="true"] {
            color: #007BFF;
            border-bottom: 2px solid #007BFF;
        }
        .sidebar .sidebar-content {
            background-color: #FFFFFF;
            box-shadow: 2px 0 5px rgba(0,0,0,0.05);
            padding: 20px;
        }
        .stTextInput div, .stTextInput input, .stTextInput textarea {
            border: none;
            background-color: #F3F4F6;
            border-radius: 6px;
            padding: 12px;
            font-size: 0.95em;
        }
        .stTextInput div:focus, .stTextInput input:focus, .stTextInput textarea:focus {
            background-color: #E5E7EB;
            box-shadow: none;
        }
        .stSelectbox div {
            border: 1px solid #E5E7EB;
            border-radius: 6px;
            padding: 8px;
        }
        a {
            color: #007BFF;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        .card {
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 20px;
            background-color: #FFFFFF;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        @media (max-width: 768px) {
            .main {
                padding: 12px;
            }
            h1 {
                font-size: 2em;
            }
            h2 {
                font-size: 1.5em;
            }
            .stMetric {
                padding: 12px;
                margin-bottom: 12px;
            }
            .stButton>button {
                padding: 8px 16px;
            }
            .stDataFrame th, .stDataFrame td {
                padding: 10px;
            }
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Sidebar: Sign-Up, Login, or Logout ---
with st.sidebar:
    st.markdown(
        """
        <hr style='border-color: #E5E7EB; margin: 12px 0;'>
        <h3 style='color: #1A1A1A; font-family: Inter, sans-serif;'>InfiBit Analytics</h3>
        """,
        unsafe_allow_html=True
    )

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
                        st.success(t("Logged in successfully!"))
                        st.rerun()
                    else:
                        st.error(t("Invalid email or password."))
                else:
                    st.error(t("Please enter email and password."))

        with tab_signup:
            new_username = st.text_input(t("Username (Optional)"), placeholder=t("Enter your username"), key="signup_username")
            new_email = st.text_input(t("Email"), placeholder=t("Enter your email"), key="signup_email")
            new_wallet = st.text_input(t("Bitcoin Wallet Address"), placeholder=t("Enter your wallet address"), key="signup_wallet")
            new_password = st.text_input(t("Password"), type="password", placeholder=t("Enter your password"), key="signup_password")
            if st.button(t("Sign Up"), use_container_width=True):
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
                                    username=new_username if new_username else "",
                                    wallet_address=new_wallet,
                                    password_hash=hash_password(new_password),
                                    created_at=datetime.now(timezone.utc).isoformat()
                                )
                                st.success(t("Signed up successfully! Please log in."))
                            except sqlite3.Error as e:
                                st.error(t("Failed to register user. Please try again."))
                                logger.error(f"Sign-up error: {e}")
                else:
                    st.error(t("Please fill out email, wallet address, and password."))
    else:
        if st.button(t("Logout"), use_container_width=True):
            st.session_state.user_email = None
            st.session_state.wallet_address = ""
            st.session_state.username = ""
            st.rerun()
        currency = st.selectbox(t("💱 Currency"), options=["USD", "GBP", "EUR"], index=0, key="currency_select")
        language_label = st.selectbox(t("🌐 Language"), options=list(LANGUAGE_OPTIONS.keys()), index=0, key="language_select")
        language = LANGUAGE_OPTIONS[language_label]
        tx_limit = st.selectbox(t("📜 Transaction Limit"), ["Last 20", "All"], index=0, help=t("Choose 'Last 20' for speed or 'All' for full history (slower for active wallets)"))

# --- Main App Logic ---
if st.session_state.user_email:
    st.markdown(
        """
        <div style='text-align: center; margin: 32px 0;'>
            <h1>Infi₿it Wallet Dashboard</h1>
            <p style='color: #4A4A4A; font-size: 1em;'>{0}</p>
        </div>
        """.format(t("Monitor your Bitcoin wallet with real-time insights")),
        unsafe_allow_html=True
    )

    # Display Username and Wallet Address
    st.markdown(
        f"""
        <div class='card'>
            <h3>{t('User Information')}</h3>
            <p><strong>{t('Username')}:</strong> {st.session_state.username}</p>
            <p><strong>{t('Bitcoin Wallet Address')}:</strong> {st.session_state.wallet_address}</p>
            <p style='color: #4A4A4A; font-size: 0.9em;'>{t('Wallet address is set at signup. Changing it is a premium feature coming soon.')}</p>
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
                    time.sleep(1)
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
    def get_btc_historical_prices():
        url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=30"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            prices = response.json().get("prices", [])
            return pd.DataFrame(prices, columns=["timestamp", "price"]).assign(
                date=lambda x: pd.to_datetime(x["timestamp"], unit="ms")
            )
        except Exception as e:
            logger.error(f"Error retrieving historical BTC prices: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=900)
    def get_currency_rates():
        url = "https://api.frankfurter.app/latest?from=USD&to=USD,GBP,EUR"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            rates = data.get("rates", {})
            rates["USD"] = 1.0
            return rates
        except Exception as e:
            logger.error(f"Error retrieving currency rates: {e}")
            return {"USD": 1.0, "GBP": 0.78, "EUR": 0.92}

    # --- Statistics Logic ---
    def get_wallet_stats(address):
        txs = get_txs_all(address)
        data = []
        total_btc_in = total_btc_out = total_usd_in = total_usd_out = 0
        first_tx_date = None

        if not txs:
            return pd.DataFrame(columns=["Date", "Type", "BTC", "USD Price at Tx", "USD Value", "TXID", "Confirmed", "Counterparty"]), 0, 0, 0, 0, None

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
                data.append([date, "IN", btc_in, btc_price, usd_in, txid, confirmed, counterparty])
            if btc_out > 0:
                usd_out = btc_out * btc_price
                total_btc_out += btc_out
                total_usd_out += usd_out
                data.append([date, "OUT", btc_out, btc_price, usd_out, txid, confirmed, counterparty])

        df = pd.DataFrame(data, columns=["Date", "Type", "BTC", "USD Price at Tx", "USD Value", "TXID", "Confirmed", "Counterparty"])
        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"])
            df["Type"] = df["Type"].astype(str)
            df["BTC"] = df["BTC"].astype(float)
            df["USD Price at Tx"] = df["USD Price at Tx"].astype(float)
            df["USD Value"] = df["USD Value"].astype(float)
        else:
            logger.warning(f"No transaction data for address: {address}")

        return df, total_btc_in, total_btc_out, total_usd_in, total_usd_out, first_tx_date

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
                wallet_value = net_btc * current_price
                invested = net_usd * multiplier if net_usd > 0 else 0
                gain = wallet_value - invested
                gain_pct = (gain / invested) * 100 if invested != 0 else 0
                avg_buy = invested / net_btc if net_btc != 0 else 0

                if net_btc < 0:
                    logger.error(f"Negative balance detected: {net_btc:.8f} BTC")
                    st.error(t("Invalid balance detected: Negative balance. Please try fetching all transactions."))
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
                for date in sorted(df["Date"].unique()) if not df.empty else []:
                    date_df = df[df["Date"] <= date]
                    net_btc_date = date_df[date_df["Type"] == "IN"]["BTC"].sum() - date_df[date_df["Type"] == "OUT"]["BTC"].sum()
                    cost_basis += date_df[date_df["Type"] == "IN"]["USD Value"].sum() - date_df[date_df["Type"] == "OUT"]["USD Value"].sum()
                    date_str = date.strftime("%d-%m-%Y")
                    price = get_historical_price(date_str)
                    value = net_btc_date * price * multiplier
                    value_data.append({"Date": date, "Market Value": value, "Cost Basis": cost_basis * multiplier})
                value_df = pd.DataFrame(value_data)
                max_drawdown = ((value_df["Market Value"] - value_df["Market Value"].cummax()) / value_df["Market Value"].cummax()).min() * 100 if not value_df.empty else 0

                # --- Tabs ---
                tab1, tab2, tab3, tab4 = st.tabs([f"💸 {t('Summary')}", f"📜 {t('Transactions')}", f"📈 {t('Portfolio')}", f"📝 {t('₿it Notes')}"])

                # --- Summary Tab ---
                with tab1:
                    st.markdown(f"<h2>{t('Wallet Overview')}</h2>", unsafe_allow_html=True)
                    if tx_limit == "Last 20":
                        st.warning(t("Note: Metrics based on last 20 transactions. Select 'All' for full accuracy."), icon="⚠️")
                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        col1, col2, col3, col4 = st.columns(4, gap="medium")
                        col1.metric(
                            t("Bitcoin Balance"),
                            f"{net_btc:.2f} BTC",
                            help=t("Total Bitcoin held in your wallet. Calculated as: Total Received BTC − Total Sent BTC, sourced from blockchain data.")
                        )
                        col2.metric(
                            t(f"Current Value ({currency})"),
                            f"{currency} {wallet_value:,.2f}",
                            help=t("Market value of your Bitcoin balance in {currency}. Calculated as: Bitcoin Balance × Current BTC Price (USD) × Currency Multiplier.").format(currency=currency)
                        )
                        col3.metric(
                            t(f"Profit/Loss ({currency})"),
                            f"{currency} {gain:,.2f}",
                            delta=f"{gain_pct:.2f}%",
                            help=t("Unrealized profit/loss in {currency}. Calculated as: Current Value − Total Invested. Percentage is relative to invested amount.").format(currency=currency)
                        )
                        col4.metric(
                            t("30-Day Volatility"),
                            f"{volatility:.2f}%",
                            help=t("Volatility (%): Annualized volatility of Bitcoin’s price over last 30 days. Calculated as: Standard Deviation of Daily Price Returns (%) × √252 × 100.")
                        )

                        col5, col6, col7, col8 = st.columns(4, gap="medium")
                        col5.metric(
                            t(f"Average Buy Price ({currency})"),
                            f"{currency} {avg_buy:,.2f}",
                            help=t("Average price paid per Bitcoin in {currency}. Calculated as: Total Invested ÷ Total Bitcoin Received.").format(currency=currency)
                        )
                        col6.metric(
                            t(f"Total Invested ({currency})"),
                            f"{currency} {invested:,.2f}",
                            help=t("Net amount spent to acquire Bitcoin in {currency}. Calculated as: Sum of (BTC Received × Price at Purchase) − Sum of (BTC Sent × Price at Sale)).").format(currency=currency)
                        )
                        col7.metric(
                            t("Holding Period"),
                            f"{holding_period_days} days",
                            help=t("Days since your first wallet transaction. Calculated as: Current Date − Date of First Transaction.")
                        )
                        col8.metric(
                            t("Sharpe Ratio"),
                            f"{sharpe_ratio:.2f}",
                            help=t("Risk-adjusted return of your investment. Calculated as: (Portfolio Return % ÷ Volatility %) × √252. Higher values indicate better risk-adjusted returns.")
                        )
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown(f"<h3>{t('Summary Metrics')}</h3>", unsafe_allow_html=True)
                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        summary_data = pd.DataFrame({
                            t("Metric"): [
                                t("Bitcoin Balance"),
                                t("Current Value"),
                                t("Total Invested"),
                                t("Profit/Loss"),
                                t("ROI (%)"),
                                t("Volatility (%)"),
                                t("Sharpe Ratio")
                            ],
                            t("Value"): [
                                f"{net_btc:.2f} BTC",
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

                # --- Transactions Tab ---
                with tab2:
                    st.markdown(f"<h2>{t('Transaction History')}</h2>", unsafe_allow_html=True)
                    df_display = df.copy()
                    df_display["USD Value"] = df_display["USD Value"] * multiplier
                    df_display["USD Price at Tx"] = df_display["USD Price at Tx"] * multiplier
                    df_display["Date"] = df_display["Date"].dt.strftime("%Y-%m-%d")

                    if not df.empty:
                        date_range = st.date_input(
                            t("Date Range:"),
                            value=[df["Date"].dt.date.min(), df["Date"].dt.date.max()],
                            min_value=df["Date"].dt.date.min(),
                            max_value=df["Date"].dt.date.max(),
                            key="date_range",
                            help=t("Select a date range to filter transactions.")
                        )
                    else:
                        date_range = st.date_input(
                            t("Date Range:"),
                            value=[datetime.now(timezone.utc).date(), datetime.now(timezone.utc).date()],
                            key="date_range",
                            help=t("Select a date range to filter transactions.")
                        )

                    filtered_df = df_display[
                        (df_display["Date"] >= date_range[0].strftime("%Y-%m-%d")) &
                        (df_display["Date"] <= date_range[1].strftime("%Y-%m-%d"))
                    ]

                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.dataframe(
                            filtered_df,
                            use_container_width=True,
                            hide_index=True
                        )
                        st.markdown("</div>", unsafe_allow_html=True)

                    with st.container():
                        st.markdown("<div class='secondary-button'>", unsafe_allow_html=True)
                        csv = filtered_df.to_csv(index=False)
                        st.download_button(
                            t("Download CSV"),
                            csv,
                            "transactions.csv",
                            "text/csv",
                            use_container_width=True,
                            key="download_csv"
                        )
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown(f"<h3>{t('Transaction Volume')}</h3>", unsafe_allow_html=True)
                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        volume_df = filtered_df.groupby("Date")["BTC"].sum().reset_index()
                        fig_volume = go.Figure()
                        fig_volume.add_trace(
                            go.Bar(
                                x=volume_df["Date"],
                                y=volume_df["BTC"],
                                name=t("Volume"),
                                marker_color="#007BFF"
                            )
                        )
                        fig_volume.update_layout(
                            title_text="",
                            xaxis_title=t("Date"),
                            yaxis_title=t("Volume (BTC)"),
                            template="plotly_white",
                            showlegend=False,
                            margin=dict(l=20, r=40, t=20, b=20)
                        )
                        st.plotly_chart(fig_volume, use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown(f"<h3>{t('Transaction Frequency')}</h3>", unsafe_allow_html=True)
                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        freq_df = filtered_df.groupby("Date")["TXID"].count().reset_index()
                        fig_freq = go.Figure()
                        fig_freq.add_trace(
                            go.Scatter(
                                x=freq_df["Date"],
                                y=freq_df["TXID"],
                                mode="lines+markers",
                                name=t("Count"),
                                line=dict(color="#007BFF")
                            )
                        )
                        fig_freq.update_layout(
                            title_text="",
                            xaxis_title=t("Date"),
                            yaxis_title=t("Number of Transactions"),
                            template="plotly_white",
                            showlegend=False,
                            margin=dict(l=20, r=40, t=20, b=20)
                        )
                        st.plotly_chart(fig_freq, use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown(f"<h3>{t('Transaction Statistics')}</h3>", unsafe_allow_html=True)
                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        col1, col2 = st.columns(2, gap="medium")
                        col1.metric(
                            t("Average BTC per Transaction"),
                            f"{filtered_df['BTC'].mean():.2f} BTC" if not filtered_df.empty else "0.0 BTC",
                            help=t("Average Bitcoin amount per transaction. Calculated as: Sum of Transaction Amounts (BTC) ÷ Number of Transactions.")
                        )
                        col2.metric(
                            t(f"Average {currency} per Transaction"),
                            f"{currency} {filtered_df['USD Value'].mean():,.2f}" if not filtered_df.empty else f"{currency} 0.00",
                            help=t("Average transaction value in {currency}. Calculated as: Sum of Transaction Values (USD) × Currency Multiplier ÷ Number of Transactions.").format(currency=currency)
                        )
                        st.markdown("</div>", unsafe_allow_html=True)

                # --- Portfolio Tab ---
                with tab3:
                    st.markdown(f"<h2>{t('Portfolio Performance')}</h2>", unsafe_allow_html=True)
                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
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
                            title_text="",
                            xaxis_title=t("Date"),
                            yaxis_title=f"{currency}",
                            template="plotly_white",
                            showlegend=True,
                            legend=dict(
                                orientation="h",
                                yanchor="bottom",
                                y=1.05,
                                xanchor="right",
                                x=1
                            ),
                            margin=dict(l=20, r=40, t=40, b=20)
                        )
                        st.plotly_chart(fig_portfolio, use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown(f"<h3>{t('Performance Metrics')}</h3>", unsafe_allow_html=True)
                    with st.container():
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        col1, col2, col3 = st.columns(3, gap="medium")
                        col1.metric(
                            t("ROI (%)"),
                            f"{gain_pct:.2f}%",
                            help=t("Return on Investment (%). Calculated as: ((Current Value − Total Invested) ÷ Total Invested × 100.)")
                        )
                        col2.metric(
                            t(f"Current BTC Price ({currency})"),
                            f"{currency} {current_price:,.2f}",
                            help=t("Current Bitcoin price in {currency}. Sourced from CoinGecko API and converted using currency rates.").format(currency=currency)
                        )
                        col3.metric(
                            t("Max Drawdown (%)"),
                            f"{max_drawdown:.2f}%",
                            help=t("Maximum percentage drop in portfolio value (%). Calculated as: Min(((Market Value − Peak Value) ÷ Peak Value) × 100.)")
                        )
                        st.markdown("</div>", unsafe_allow_html=True)

                # --- ₿it Notes Tab ---
                with tab4:
                    st.markdown(f"<h2>{t('₿it Notes')}</h2>", unsafe_allow_html=True)
                    st.write(t("Share your thoughts on Bitcoin or track your investment notes."))
                    with st.form("notes_form", clear_on_submit=True):
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.subheader(t("Add a New Note"))
                        note_title = st.text_input("", placeholder=t("Note Title"), max_chars=100, key="note_title")
                        note_description = st.text_area("", placeholder=t("Description"), max_chars=500, key="note_description")
                        note_content = st.text_area("", placeholder=t("Content"), max_chars=1000, key="note_content")
                        if st.form_submit_button(t("Submit Note"), use_container_width=True):
                            if note_title and note_description and note_content:
                                try:
                                    save_note(
                                        user_email=st.session_state.user_email,
                                        title=note_title,
                                        description=note_description,
                                        content=note_content,
                                        created_at=datetime.now(timezone.utc).isoformat()
                                    )
                                    st.success(t("Note added successfully!"))
                                    st.rerun()
                                except sqlite3.Error as e:
                                    st.error(t("Failed to save note. Please try again."))
                                    logger.error(f"Note save error: {e}")
                            else:
                                st.error(t("Please fill out all fields!"))
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown(f"<h3>{t('Your Notes')}</h3>", unsafe_allow_html=True)
                    notes = load_user_notes(st.session_state.user_email)
                    if notes:
                        for note in notes:
                            with st.expander(f"{note['title']}", expanded=False):
                                st.markdown(
                                    f"""
                                    <div class='card'>
                                        <p><strong>{t('Title')}:</strong> {note['title']}</p>
                                        <p><strong>{t('Description')}:</strong> {note['description']}</p>
                                        <p><strong>{t('Content')}:</strong> {note['content']}</p>
                                        <p><strong>{t('Date')}:</strong> {note['date']}</p>
                                        <p><strong>{t('Author')}:</strong> {note['author']}</p>
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                    else:
                        st.info(t("No notes yet. Add your first note above!"), icon="ℹ️")

    else:
        st.warning(t("Please log in to view your wallet insights."), icon="⚠️")

    # --- Footer ---
    st.markdown(
        """
        <div class='card'>
            <hr style='border-color: #E5E7EB; margin: 20px 0'>
            <p style='color: #4A4A4A; font-size: 0.9em;'>© 2025 InfiBit Analytics. All rights reserved.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

else:
    st.markdown(
        """
        <div style='text-align: center; margin: 64px 0;'>
            <h1>Welcome to Infi₿it Analytics!</h1>
            <p style='color: #4A4A4A; font-size: 1.1em;'>{0}</p>
            <p style='color: #4A4A4A;'>{1}</p>
        </div>
        """.format(
            t("Monitor your Bitcoin wallet with real-time insights"),
            t("Please sign up or log in to access the dashboard.")
        ),
        unsafe_allow_html=True
    )