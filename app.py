import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone, date
from datetime import timedelta
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
import urllib.parse

# Load environment variables
load_dotenv()
GOCARDLESS_API_KEY = os.getenv("GOCARDLESS_API_KEY") 
GOCARDLESS_PLAN_ID = "BRT0003XM6FHXA5"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Database Functions ---
@contextmanager
def get_db_connection():
    try:
        conn = sqlite3.connect("infibit.db")
        conn.row_factory = sqlite3.Row
        logger.debug("SQLite connection established with row_factory set to sqlite3.Row")
        try:
            yield conn
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.error(f"Error accessing database: {e}")
        raise

def init_db_socket():
    """Initialize database with schema, adding subscription_start_date."""
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
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            if "gocardless_customer_id" not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN gocardless_customer_id TEXT")
                logger.info("Added gocardless_customer_id column.")
            if "subscription_status" not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN subscription_status TEXT")
                logger.info("Added subscription_status column.")
            if "mandate_id" not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN mandate_id TEXT")
                logger.info("Added mandate_id column.")
            if "subscription_start_date" not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN subscription_start_date TEXT")
                logger.info("Added subscription_start_date column.")
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
    """Load users from database."""
    users = {}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, email, wallet_address, password_hash, created_at, gocardless_customer_id, subscription_status, mandate_id, subscription_start_date FROM users")
            rows = cursor.fetchall()
            logger.debug(f"Fetched {len(rows)} users")
            for row in rows:
                if isinstance(row, sqlite3.Row):
                    users[row["email"]] = {
                        "username": row["username"],
                        "wallet_address": row["wallet_address"],
                        "password_hash": row["password_hash"],
                        "created_at": row["created_at"],
                        "gocardless_customer_id": row["gocardless_customer_id"],
                        "subscription_status": row["subscription_status"],
                        "mandate_id": row["mandate_id"],
                        "subscription_start_date": row["subscription_start_date"]
                    }
                else:
                    users[row[1]] = {
                        "username": row[0],
                        "wallet_address": row[2],
                        "password_hash": row[3],
                        "created_at": row[4],
                        "gocardless_customer_id": row[5] if len(row) > 5 else None,
                        "subscription_status": row[6] if len(row) > 6 else None,
                        "mandate_id": row[7] if len(row) > 7 else None,
                        "subscription_start_date": row[8] if len(row) > 8 else None
                    }
            logger.info(f"Loaded {len(users)} users")
        return users
    except sqlite3.Error as e:
        logger.error(f"Error loading users: {e}")
        return {}

def save_user(email, username, wallet_address, password_hash, created_at, gocardless_customer_id=None, subscription_status=None, mandate_id=None, subscription_start_date=None):
    """Save a new user to the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (email, username, wallet_address, password_hash, created_at, gocardless_customer_id, subscription_status, mandate_id, subscription_start_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (email, username, wallet_address, password_hash, created_at, gocardless_customer_id, subscription_status, mandate_id, subscription_start_date))
            conn.commit()
        logger.info(f"User {email} saved successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to save user {email}: {e}")
        raise

def update_subscription_status(email, gocardless_customer_id=None, subscription_status=None, mandate_id=None, subscription_start_date=None):
    """Update subscription details for a user."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users
                SET gocardless_customer_id = ?,
                    subscription_status = ?,
                    mandate_id = ?,
                    subscription_start_date = ?
                WHERE email = ?
            """, (gocardless_customer_id, subscription_status, mandate_id, subscription_start_date, email))
            conn.commit()
        logger.info(f"Subscription updated for user {email}")
    except sqlite3.Error as e:
        logger.error(f"Error updating subscription for {email}: {e}")
        raise

def get_user_subscription(email):
    """Retrieve subscription details for a user."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT gocardless_customer_id, subscription_status, mandate_id, subscription_start_date FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            if row:
                if isinstance(row, sqlite3.Row):
                    return {
                        "gocardless_customer_id": row["gocardless_customer_id"],
                        "subscription_status": row["subscription_status"],
                        "mandate_id": row["mandate_id"],
                        "subscription_start_date": row["subscription_start_date"]
                    }
                else:
                    return {
                        "gocardless_customer_id": row[0],
                        "subscription_status": row[1],
                        "mandate_id": row[2],
                        "subscription_start_date": row[3]
                    }
        return {}
    except sqlite3.Error as e:
        logger.error(f"Error fetching subscription for {email}: {e}")
        return {}

def save_note(user_email, title, description, content, created_at):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notes (user_email, title, description, content, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_email, title, description, content, created_at))
            conn.commit()
        logger.info(f"Note '{title}' saved for user {user_email}")
    except sqlite3.Error as e:
        logger.error(f"Error saving note: {e}")
        raise

def load_user_notes(user_email):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notes WHERE user_email = ?", (user_email,))
            rows = cursor.fetchall()
            notes = [
                {
                    "id": row["id"] if isinstance(row, sqlite3.Row) else row[0],
                    "title": row["title"] if isinstance(row, sqlite3.Row) else row[2],
                    "description": row["description"] if isinstance(row, sqlite3.Row) else row[3],
                    "content": row["content"] if isinstance(row, sqlite3.Row) else row[4],
                    "date": row["created_at"] if isinstance(row, sqlite3.Row) else row[5],
                    "author": row["user_email"] if isinstance(row, sqlite3.Row) else row[1]
                }
                for row in rows
            ]
        logger.info(f"Loaded {len(notes)} notes for user {user_email}")
        return notes
    except sqlite3.Error as e:
        logger.error(f"Error loading notes for {user_email}: {e}")
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
            logger.info(f"Migrated {len(json_users)} users from JSON")
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
            logger.info(f"Migrated {len(json_notes)} notes from JSON")
            os.rename("bit_notes.json", "bit_notes.json.bak")
        except Exception as e:
            logger.error(f"Error migrating notes: {e}")

# Initialize database and migrate data
try:
    init_db_socket()
    migrate_users_from_json()
    migrate_notes_from_json()
except Exception as e:
    logger.error(f"Database initialization failed: {e}")
    st.error("Database initialization failed. Please check logs.")

# --- GoCardless API Function ---
def check_subscription_status(customer_id, subscription_status=None):
    """Check GoCardless mandate status, but preserve active status for new subscriptions."""
    if subscription_status == "active":
        return "active", None
    if not customer_id:
        return "inactive", None
    url = f"https://api.gocardless.com/customers/{customer_id}/mandates"
    headers = {
        "Authorization": f"Bearer {GOCARDLESS_API_KEY}",
        "GoCardless-Version": "2015-07-06"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        mandates = response.json().get("mandates", [])
        for mandate in mandates:
            if mandate["status"] in ["active", "pending_submission"]:
                return "active", mandate["id"]
        return "inactive", None
    except Exception as e:
        logger.error(f"Error checking subscription for customer {customer_id}: {e}")
        return "inactive", None

# --- Page Configuration ---
st.set_page_config(
    page_title="InfiBit | Bitcoin Wallet Dashboard",
    layout="wide",
    page_icon="₿",
    initial_sidebar_state="expanded",
)

# --- CSS for Blurred Paywall and Styling ---
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
        .blur {
            filter: blur(5px);
            pointer-events: none;
            user-select: none;
        }
        .paywall-container {
            position: relative;
            text-align: center;
            margin-top: 50px;
        }
        .paywall-message {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background-color: rgba(255, 255, 255, 0.9);
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
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
            font-weight: bold;
            color: #4A4A4A;
            margin-bottom: 5px;
            display: flex;
            align-items: center;
        }
        .stMetric .metric-value {
            font-size: 1.3em;
            font-weight: bold;
            color: #333;
        }
        h1, h2, h3, h4 {
            font-family: 'Inter', sans-serif;
            color: #1A1A1A;
            font-weight: bold;
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
            background-color: #007BFF;
            color: white;
            border-radius: 6px;
            font-weight: 500;
            padding: 8px 16px;
            border: none;
            transition: background-color 0.2s;
        }
        .stButton>button:hover {
            background-color: #333;
        }
        .stDataFrame {
            border-collapse: collapse;
            width: auto 100%;
            font-size: 14px;
        }
        .stDataFrame th {
            background-color: #F5F6F5;
            color: white #333;
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }
        .stDataFrame td {
            padding: 4px 12px;
            border-bottom: 2px solid #E0E0E0;
        }
        .stDataFrame tr:nth-child(even) {
            background-color: #FAFAFA;
        }
        .stSpinner div {
            color: #007BFF;
        }
        .stTabs [data-baseweb="tab"] {
            font-size: 14px;
            font-weight: 500;
            padding: 10px 20px;
            color: #333;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: #007BFF;
        }
        .sidebar .sidebar-content {
            background-color: #FFF;
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
if "language" not in st.session_state:
    st.session_state.language = "en"

# --- Translate Function ---
def t(text):
    if st.session_state.language == "en":
        return text
    try:
        return GoogleTranslator(source="en", target=st.session_state.language).translate(text)
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
if "language" not in st.session_state:
    st.session_state.language = "en"
if "tx_limit" not in st.session_state:
    st.session_state.tx_limit = "Last 20"

# --- Sidebar: Sign-Up, Login, or Logout ---
with st.sidebar:
    st.markdown(
        """
        <hr style='border-color: #E0E0E0; margin: 10px 0;'>
        <h3 style='color: #1A1A1A; font-family: Inter, sans-serif;'>InfiBit Analytics</h3>
        """,
        unsafe_allow_html=True
    )

    if not st.session_state.user_email:
        tab_login, tab_signup = st.tabs([t("Login"), t("Sign Up")])

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
                        st.session_state.username = user["username"] or email
                        st.session_state.language = "en"
                        st.success(t("Logged in successfully!"))
                        st.rerun()
                    else:
                        st.error(t("Invalid email or password."))
                else:
                    st.error(t("Please enter email and password."))

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
                            except sqlite3.Error as e:
                                st.error(t("Failed to register user. Please try again."))
                                logger.error(f"Sign-up error: {e}")
                else:
                    st.error(t("Please fill out email, wallet address, and password."))
    else:
        if st.button(t("Logout")):
            st.session_state.user_email = None
            st.session_state.wallet_address = ""
            st.session_state.username = ""
            st.session_state.language = "en"
            st.session_state.tx_limit = "Last 20"
            st.rerun()
        currency = st.selectbox(t("💱 Currency"), options=["USD", "GBP", "EUR"], index=0, key="currency_select")
        language_label = st.selectbox(t("🌐 Language"), options=list(LANGUAGE_OPTIONS.keys()), index=0, key="language_select")
        st.session_state.language = LANGUAGE_OPTIONS[language_label]
        st.session_state.tx_limit = st.selectbox(t("📜 Transaction Limit"), ["Last 20", "All"], index=0, help=t("Choose 'Last 20' for speed or 'All' for full history (slower for active wallets)"))

# --- Main App Logic ---
if st.session_state.user_email:
    subscription_info = get_user_subscription(st.session_state.user_email)
    subscription_status, mandate_id = check_subscription_status(
        subscription_info.get("gocardless_customer_id"),
        subscription_info.get("subscription_status")
    )

    if subscription_info.get("subscription_status") != subscription_status or subscription_info.get("mandate_id") != mandate_id:
        update_subscription_status(
            st.session_state.user_email,
            subscription_info.get("gocardless_customer_id"),
            subscription_status,
            mandate_id,
            subscription_info.get("subscription_start_date")
        )

    if subscription_status != "active":
        if st.button(t("Subscribe to Premium")):
            try:
                # Validate email
                if not st.session_state.user_email or not st.session_state.user_email.strip():
                    logger.error("No valid email in session state")
                    st.error(t("No valid email found. Please log in again."))
                else:
                    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                    if not re.match(email_pattern, st.session_state.user_email):
                        logger.error(f"Invalid email format: {st.session_state.user_email}")
                        st.error(t("Invalid email format. Ensure your email is valid (e.g., user@example.com)."))
                    else:
                        # Set subscription to active
                        update_subscription_status(
                            st.session_state.user_email,
                            gocardless_customer_id=None,
                            subscription_status="active",
                            mandate_id=None,
                            subscription_start_date=datetime.now(timezone.utc).isoformat()
                        )
                        logger.info(f"Activated premium access for user {st.session_state.user_email}")

                        # Display GoCardless redirect button
                        redirect_url = f"https://pay.gocardless.com/BRT0003XM6FHXA5?email={urllib.parse.quote(st.session_state.user_email)}"
                        st.markdown(
                            f'<a href="{redirect_url}" target="_blank"><button style="border-radius: 6px; background-color: #007BFF; color: #FFFFFF; padding: 8px; border: none;">{t("Complete Payment Setup")}</button></a>',
                            unsafe_allow_html=True
                        )
                        st.success(t("Premium will activate when you complete the payment setup."))
            except Exception as e:
                logger.error(f"Error initiating subscription for {st.session_state.user_email}: {e}")
                st.error(t("Failed to initiate subscription. Please try again or contact support."))
        st.markdown(
            """
            <div class='blur'>
                <div style='text-align: center; margin-top: 30px;'>
                    <h1>Infi₿it Wallet Dashboard</h1>
                    <p style='color: #4A4A4A; font-size: 1em;'>{0}</p>
                </div>
                <div style='border: 1px solid #E0E0E0; border-radius: 8px; padding: 15px; margin-bottom: 20px;'>
                    <h3>{1}</h3>
                    <p><strong>{2}:</strong> {3}</p>
                    <p><strong>{4}:</strong> {5}</p>
                    <p style='color: #4A4A4A; font-size: 0.9em;'>{6}</p>
                </div>
            </div>
            <div class='paywall-container'>
                <div class='paywall-message'>
                    <h2>{7}</h2>
                    <p>{8}</p>
                </div>
            </div>
            """.format(
                t("Monitor your Bitcoin wallet with real-time insights"),
                t("User Information"),
                t("Username"),
                st.session_state.username,
                t("Bitcoin Wallet Address"),
                st.session_state.wallet_address,
                t("Wallet address is set at signup. Changing it is a premium feature coming soon."),
                t("Unlock Full Access"),
                t("Subscribe to InfiBit Analytics Premium for £10/month to access all features.")
            ),
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div style='text-align: center; margin-top: 30px;'>
                <h1>Infi₿it Wallet Dashboard</h1>
                <p style='color: #4A4A4A; font-size: 1em;'>{0}</p>
            </div>
            """.format(t("Monitor your Bitcoin wallet with real-time insights")),
            unsafe_allow_html=True
        )

        st.markdown(
            f"""
            <div style='border: 1px solid #E0E0E0; border-radius: 8px; padding: 15px; margin-bottom: 20px;'>
                <h3>{t("User Information")}</h3>
                <p><strong>{t("Username")}:</strong> {st.session_state.username}</p>
                <p><strong>{t("Bitcoin Wallet")}:</strong> {st.session_state.wallet_address}</p>
                <p style='color: #4A4A4A; font-size: 0.9em;'>{t("Wallet address is set at signup. Changing it is a premium feature.")}</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        price_cache = {}

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
                return 0

        @st.cache_data(ttl=3600)
        def get_txs_all(address):
            all_txs = []
            url = f"https://blockstream.info/api/address/{address}/txs"
            try:
                logger.info(f"Fetching transactions for address: {address}")
                if st.session_state.tx_limit == "Last 20":
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
                counterparties = [
                    vin.get("prevout", {}).get("scriptpubkey_address", "") for vin in detail.get("vin", []) if vin.get("prevout", {}).get("scriptpubkey_address") != address
                ] or [
                    v.get("scriptpubkey_address") for v in detail.get("vout", []) if v.get("scriptpubkey_address") != address
                ]
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

                logger.debug(f"Tx {txid}: IN={btc_in:.8f}, OUT={btc_out:.8f}, Price={btc_price:.2f}")

            df = pd.DataFrame(data, columns=["Date", "Type", "BTC", "Price at Tx", "USD Value", "Txid", "Confirmed", "Counterparty"])
            if not df.empty:
                df["Date"] = pd.to_datetime(df["Date"], format="%d-%m-%Y")
                df["Type"] = df["Type"].astype(str)
                df["BTC"] = df["BTC"].astype(float)
                df["Price at Tx"] = df["Price at Tx"].astype(float)
                df["USD Value"] = df["USD Value"].astype(float)
            else:
                logger.warning(f"No transaction data for address: {address}")

            return df, total_btc_in, total_btc_out, total_usd_in, total_usd_out, first_tx_date

        currency_rates = get_currency_rates()
        multiplier = currency_rates.get(currency.upper(), 1.0)

        if st.session_state.wallet_address:
            with st.container():
                with st.spinner(t("Loading wallet insights...")):
                    df, total_btc_in, total_btc_out, usd_in, usd_out, first_tx_date = get_wallet_stats(st.session_state.wallet_address)
                    if isinstance(df, pd.DataFrame) and df.empty:
                        st.warning(t("No transactions found for this wallet."))
                    current_price_usd = get_current_btc_price()
                    net_btc = get_wallet_balance(st.session_state.wallet_address)
                    if net_btc == 0 and not isinstance(df, pd.DataFrame):
                        st.error(t("Failed to fetch wallet balance. Please try again later."))

                    current_price = current_price_usd * multiplier
                    net_usd = usd_in - usd_out
                    wallet_value_usd = net_btc * current_price_usd
                    wallet_value = wallet_value_usd * multiplier
                    invested = net_usd * multiplier if total_btc_in > 0 else wallet_value
                    gain = wallet_value - invested
                    gain_pct = (gain / invested) * 100 if invested != 0 else 0
                    avg_buy = invested / net_btc if net_btc != 0 else 0

                    if net_btc < 0:
                        logger.error(f"Invalid balance detected: {net_btc:.8f} BTC")
                        st.error(t("Error: Invalid balance detected. Please try fetching all transactions."))
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
                        date_df = df[df["Date"] == date]
                        net_btc_date = sum(df[df["Type"] == "IN"]["BTC"]) - sum(df[df["Type"] == "OUT"]["BTC"])
                        cost_basis += date_df[date_df["Type"] == "IN"]["USD Value"].sum() - date_df[date_df["Type"] == "OUT"]["USD Value"].sum()
                        date_str = pd.to_datetime(date).strftime("%d-%m-%Y")
                        price = get_historical_price(date_str)
                        value = net_btc_date * price * multiplier
                        value_data.append({"Date": date, "Market Value": value, "Cost Basis": cost_basis * multiplier})
                    value_df = pd.DataFrame(value_data)
                    max_drawdown = (
                        (value_df["Market Value"] - value_df["Market Value"].cummax()) / value_df["Market Value"].cummax()
                    ).min() * 100 if not value_df.empty else 0

                    tab1, tab2, tab3, tab4 = st.tabs([t("Summary"), t("Transactions"), t("Portfolio"), t("₿it Notes")])

                    with tab1:
                        st.markdown(f"### 💼 {t('Wallet Overview')}")
                        if st.session_state.tx_limit == "Last 20":
                            st.warning(t("Showing metrics based on the last 20 transactions. For full accuracy, select 'All' transactions."))
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric(t("Bitcoin Balance"), f"{net_btc:.8f} BTC", help=t("Total Bitcoin in your wallet"))
                        col2.metric(f"{t('Current Value')} ({currency})", f"{wallet_value:,.2f}", help=t("Current market value of your Bitcoin"))
                        col3.metric(f"{t('Profit/Loss')} ({currency})", f"{gain:.2f}", delta=f"{gain_pct:.2f}%", help=t("Unrealized profit or loss"))
                        col4.metric(t("30-Day Volatility"), f"{volatility:.2f}%", help=t("Annualized price volatility of Bitcoin"))

                        col5, col6, col7, col8 = st.columns(4)
                        col5.metric(f"{t('Average Buy Price')} ({currency})", f"{avg_buy:.2f}", help=t("Average price paid per Bitcoin"))
                        col6.metric(f"{t('Total Invested')} ({currency})", f"{invested:.2f}", help=t("Total amount invested"))
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
                                f"{currency} {wallet_value:.2f}",
                                f"{currency} {invested:.2f}",
                                f"{currency} {gain:.2f}",
                                f"{gain_pct:.2f}%",
                                f"{volatility:.2f}%",
                                f"{sharpe_ratio:.2f}"
                            ]
                        }
                        st.dataframe(pd.DataFrame(summary_data), use_container_width=True)

                    with tab2:
                        st.markdown(f"### 📜 {t('Transaction History')}")
                        df_display = df.copy()
                        df_display["USD Value"] = df_display["USD Value"] * multiplier
                        df_display["Date"] = df_display["Date"].dt.strftime("%Y-%m-%d")

                        if not df.empty:
                            date_range = st.date_input(
                                t("Date Range"),
                                [df["Date"].min(), df["Date"].max()],
                                min_value=df["Date"].min(),
                                max_value=df["Date"].max(),
                                key="date_range"
                            )
                            filtered_df = df_display[
                                (df_display["Date"] >= date_range[0].strftime("%Y-%m-%d")) &
                                (df_display["Date"] <= date_range[1].strftime("%Y-%m-%d"))
                            ]
                        else:
                            date_range = st.date_input(
                                t("Date Range"),
                                [date.today() - timedelta(days=30), date.today()],
                                key="date_range",
                                disabled=True
                            )
                            filtered_df = pd.DataFrame()

                        st.dataframe(
                            filtered_df[["Date", "Type", "BTC", "USD Value", "Price at Tx", "Txid", "Confirmed", "Counterparty"]],
                            use_container_width=True
                        )

                        csv = filtered_df.to_csv(index=False)
                        st.download_button(
                            t("Download Transactions as CSV"),
                            csv,
                            "transactions.csv",
                            "text/csv",
                            key="download_transactions_csv"
                        )

                        st.markdown(f"### 📈 {t('Transaction Volume')}")
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

                        st.markdown(f"### 📉 {t('Transaction Frequency')}")
                        freq_df = filtered_df.groupby("Date")["Txid"].count().reset_index(name="Count")
                        fig_freq = go.Figure()
                        fig_freq.add_trace(
                            go.Scatter(
                                x=freq_df["Date"],
                                y=freq_df["Count"],
                                mode="lines+markers",
                                name=t("Transaction Count"),
                                line=dict(color="#FF5733")
                            )
                        )
                        fig_freq.update_layout(
                            title=t("Transaction Frequency Over Time"),
                            xaxis_title=t("Date"),
                            yaxis_title=t("Number of Transactions"),
                            template="plotly_white"
                        )
                        st.plotly_chart(fig_freq, use_container_width=True)

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
                            title=t("Portfolio Value vs Cost Basis"),
                            xaxis_title=t("Date"),
                            yaxis_title=f"{currency}",
                            template="plotly_white"
                        )
                        st.plotly_chart(fig_portfolio, use_container=True)

                        st.markdown(f"### 📊 {t('Performance Metrics')}")
                        col1, col2, col3 = st.columns(3)
                        col1.metric(t("ROI"), f"{gain_pct:.2f}%", help=t("Return on investment"))
                        col2.metric(f"{t('Current BTC Price')} ({currency})", f"{currency} {current_price:,.2f}", help=t("Current market price"))
                        col3.metric(t("Max Drawdown"), f"{max_drawdown:.2f}%", help=t("Maximum portfolio value drop"))

                    with tab4:
                        st.markdown(f"### 📝 {t('₿it Notes')}")
                        st.info(t("Create and manage your notes related to your Bitcoin wallet activities."))
                        notes = load_user_notes(st.session_state.user_email)
                        if notes:
                            st.subheader(t("Your Notes"))
                            for note in notes:
                                with st.expander(f"{note['title']} ({note['date']})"):
                                    st.write(f"**{t('Description')}:** {note['description']}")
                                    st.write(f"**{t('Content')}:** {note['content']}")
                        else:
                            st.write(t("No notes found. Create a new note below."))

                        st.subheader(t("Create New Note"))
                        with st.form("note_form"):
                            title = st.text_input(t("Title"), max_chars=100)
                            description = st.text_input(t("Description"), max_chars=200)
                            content = st.text_area(t("Content"), height=150)
                            submitted = st.form_submit_button(t("Save Note"))
                            if submitted:
                                if title and description and content:
                                    try:
                                        save_note(
                                            user_email=st.session_state.user_email,
                                            title=title,
                                            description=description,
                                            content=content,
                                            created_at=datetime.now(timezone.utc).isoformat()
                                        )
                                        st.success(t("Note saved successfully!"))
                                        st.rerun()
                                    except sqlite3.Error as e:
                                        st.error(t("Failed to save note. Please try again."))
                                        logger.error(f"Note save error: {e}")
                                else:
                                    st.error(t("Please fill out all fields."))

else:
    st.markdown(
        """
        <div style='text-align: center; margin-top: 50px;'>
            <h1>Welcome to InfiBit</h1>
            <p style='color: #4A4A4A; font-size: 1.1em;'>{0}</p>
            <p style='color: #4A4A4A'>{1}</p>
        </div>
        """.format(
            t("Monitor your Bitcoin wallet with real-time insights"),
            t("Please sign up or login to access the dashboard.")
        ),
        unsafe_allow_html=True
    )