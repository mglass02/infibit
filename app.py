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
import re
import logging
import sqlite3
from contextlib import contextmanager
import bcrypt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Database Functions ---
@contextmanager
def get_db_connection():
    """Manage SQLite database connections with proper commit and close."""
    try:
        conn = sqlite3.connect("infibit.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        logger.debug("SQLite connection established")
        yield conn
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error accessing database: {e}")
        raise
    finally:
        conn.close()

def init_db():
    """Initialize database with schema for users."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    wallet_address TEXT UNIQUE NOT NULL,
                    name TEXT,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error initializing database: {e}")
        raise

def load_user_by_email(email):
    """Load user by email from database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT email, wallet_address, name, password_hash, created_at
                FROM users WHERE email = ?
            """, (email,))
            row = cursor.fetchone()
            if row:
                return {
                    "email": row["email"],
                    "wallet_address": row["wallet_address"],
                    "name": row["name"],
                    "password_hash": row["password_hash"],
                    "created_at": row["created_at"]
                }
        return None
    except sqlite3.Error as e:
        logger.error(f"Error loading user {email}: {e}")
        return None

def load_user_by_wallet(wallet_address):
    """Load user by wallet address from database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT email, wallet_address, name, password_hash, created_at
                FROM users WHERE wallet_address = ?
            """, (wallet_address,))
            row = cursor.fetchone()
            if row:
                return {
                    "email": row["email"],
                    "wallet_address": row["wallet_address"],
                    "name": row["name"],
                    "password_hash": row["password_hash"],
                    "created_at": row["created_at"]
                }
        return None
    except sqlite3.Error as e:
        logger.error(f"Error loading user {wallet_address}: {e}")
        return None

def save_user(wallet_address, name, email, password, created_at):
    """Save a new user to the database with hashed password."""
    try:
        password_hash = hash_password(password)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users (email, wallet_address, name, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (email, wallet_address, name if name else None, password_hash, created_at))
        logger.info(f"User with email {email} saved successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to save user {email}: {e}")
        raise

# --- Password Hashing ---
def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

# --- Wallet Address Validation ---
def validate_wallet_address(address):
    pattern = r'^(bc1|[13])[a-zA-Z0-9]{25,61}$'
    return re.match(pattern, address) is not None

# Initialize database
try:
    init_db()
except Exception as e:
    logger.error(f"Database initialization failed: {e}")
    st.error("Database initialization failed. Please check logs.")

# --- Page Configuration ---
st.set_page_config(
    page_title="InfiBit | Bitcoin Wallet Dashboard",
    layout="wide",
    page_icon="₿",
    initial_sidebar_state="expanded",
)

# --- CSS Styling ---
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body {
            background-color: #FFFFFF;
            color: #1A1A1A;
            font-family: 'Inter', sans-serif;
        }
        .main {
            padding: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }
        .stMetric {
            background-color: #FFFFFF;
            border: 1px solid #E0E0E0;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            margin-bottom: 15px;
        }
        .stMetric label {
            font-size: 0.9em;
            font-weight: bold;
            color: #4A4A4A;
        }
        .stMetric .metric-value {
            font-size: 1.3em;
            font-weight: bold;
            color: #333;
        }
        h1, h2, h3 {
            font-family: 'Inter', sans-serif;
            color: #1A1A1A;
            font-weight: bold;
        }
        h1 {
            font-size: 2.2em;
        }
        h2 {
            font-size: 1.5em;
        }
        .stButton>button {
            background-color: #007BFF;
            color: white;
            border-radius: 6px;
            padding: 8px 16px;
            border: none;
        }
        .stDataFrame th {
            background-color: #F5F6F5;
            color: #333;
            padding: 12px;
            font-weight: bold;
        }
        .stDataFrame td {
            padding: 4px 12px;
            border-bottom: 2px solid #E0E0E0;
        }
        .sidebar .sidebar-content {
            background-color: #FFF;
            box-shadow: 2px 0 5px rgba(0,0,0,0.05);
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

# --- Session State Initialization ---
if "user" not in st.session_state:
    st.session_state.user = None
if "language" not in st.session_state:
    st.session_state.language = "en"
if "currency" not in st.session_state:
    st.session_state.currency = "USD"
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# --- Sidebar ---
with st.sidebar:
    st.markdown(
        """
        <hr style='border-color: #E0E0E0; margin: 10px 0;'>
        <h3 style='color: #1A1A1A; font-family: Inter, sans-serif;'>Infi₿it Analytics</h3>
        """,
        unsafe_allow_html=True
    )

    if not st.session_state.authenticated:
        # Login and Signup Tabs
        login_tab, signup_tab = st.tabs([t("Login"), t("Signup")])

        with login_tab:
            with st.form("login_form"):
                login_email = st.text_input(t("Email"), key="login_email")
                login_password = st.text_input(t("Password"), type="password", key="login_password")
                if st.form_submit_button(t("Login")):
                    if login_email and login_password:
                        user = load_user_by_email(login_email)
                        if user and verify_password(login_password, user["password_hash"]):
                            st.session_state.user = user
                            st.session_state.authenticated = True
                            st.success(t("Login successful! Accessing dashboard..."))
                            st.rerun()
                        else:
                            st.error(t("Invalid email or password."))
                    else:
                        st.error(t("Please provide both email and password."))

        with signup_tab:
            with st.form("signup_form"):
                wallet_input = st.text_input(t("Bitcoin Wallet Address"), key="signup_wallet")
                name = st.text_input(t("Name (Optional)"), key="signup_name")
                signup_email = st.text_input(t("Email"), key="signup_email")
                signup_password = st.text_input(t("Password"), type="password", key="signup_password")
                if st.form_submit_button(t("Sign Up")):
                    if not wallet_input:
                        st.error(t("Please provide a Bitcoin wallet address."))
                    elif not validate_wallet_address(wallet_input):
                        st.error(t("Invalid Bitcoin address (must start with 'bc1', '1', or '3', 26–62 characters)."))
                    elif not signup_email:
                        st.error(t("Please provide an email address."))
                    elif not signup_password:
                        st.error(t("Please provide a password."))
                    else:
                        try:
                            save_user(
                                wallet_address=wallet_input,
                                name=name,
                                email=signup_email,
                                password=signup_password,
                                created_at=datetime.now(timezone.utc).isoformat()
                            )
                            st.session_state.user = load_user_by_email(signup_email)
                            st.session_state.authenticated = True
                            st.success(t("Sign up successful! Accessing dashboard..."))
                            st.rerun()
                        except sqlite3.Error:
                            st.error(t("Failed to save user details. Email or wallet address may already be in use."))
    else:
        if st.button(t("Clear Wallet")):
            st.session_state.user = None
            st.session_state.authenticated = False
            st.rerun()
        st.session_state.currency = st.selectbox(t("💱 Currency"), options=["USD", "GBP", "EUR"], index=0, key="currency_select")
        language_label = st.selectbox(t("🌐 Language"), options=list(LANGUAGE_OPTIONS.keys()), index=0, key="language_select")
        st.session_state.language = LANGUAGE_OPTIONS[language_label]

# --- Main App Logic ---
if st.session_state.authenticated and st.session_state.user:
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
            <h3>{t("Wallet Information")}</h3>
            <p><strong>{t("Bitcoin Wallet Address")}:</strong> {st.session_state.user['wallet_address']}</p>
            <p><strong>{t("Name")}:</strong> {st.session_state.user.get('name', 'Not provided')}</p>
            <p><strong>{t("Email")}:</strong> {st.session_state.user.get('email', 'Not provided')}</p>
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
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            txs = response.json()
            all_txs.extend(txs[:20])
            logger.info(f"Fetched {len(all_txs)} transactions (limited to 20)")
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
    multiplier = currency_rates.get(st.session_state.currency.upper(), 1.0)

    with st.container():
        with st.spinner(t("Loading wallet insights...")):
            df, total_btc_in, total_btc_out, usd_in, usd_out, first_tx_date = get_wallet_stats(st.session_state.user['wallet_address'])
            if isinstance(df, pd.DataFrame) and df.empty:
                st.warning(t("No transactions found for this wallet."))
            current_price_usd = get_current_btc_price()
            net_btc = get_wallet_balance(st.session_state.user['wallet_address'])
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
                st.error(t("Error: Invalid balance detected. Please try again later."))
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

            tab1, tab2, tab3 = st.tabs([t("Summary"), t("Transactions"), t("Portfolio")])

            with tab1:
                st.markdown(f"### 💼 {t('Wallet Overview')}")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric(t("Bitcoin Balance"), f"{net_btc:.8f} BTC", help=t("Total Bitcoin in your wallet"))
                col2.metric(f"{t('Current Value')} ({st.session_state.currency})", f"{wallet_value:,.2f}", help=t("Current market value of your Bitcoin"))
                col3.metric(f"{t('Profit/Loss')} ({st.session_state.currency})", f"{gain:.2f}", delta=f"{gain_pct:.2f}%", help=t("Unrealized profit or loss"))
                col4.metric(t("30-Day Volatility"), f"{volatility:.2f}%", help=t("Annualized price volatility of Bitcoin"))

                col5, col6, col7, col8 = st.columns(4)
                col5.metric(f"{t('Average Buy Price')} ({st.session_state.currency})", f"{avg_buy:.2f}", help=t("Average price paid per Bitcoin"))
                col6.metric(f"{t('Total Invested')} ({st.session_state.currency})", f"{invested:.2f}", help=t("Total amount invested"))
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
                        f"{st.session_state.currency} {wallet_value:.2f}",
                        f"{st.session_state.currency} {invested:.2f}",
                        f"{st.session_state.currency} {gain:.2f}",
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
                    yaxis_title=f"{st.session_state.currency}",
                    template="plotly_white"
                )
                st.plotly_chart(fig_portfolio, use_container_width=True)

                st.markdown(f"### 📊 {t('Performance Metrics')}")
                col1, col2, col3 = st.columns(3)
                col1.metric(t("ROI"), f"{gain_pct:.2f}%", help=t("Return on investment"))
                col2.metric(f"{t('Current BTC Price')} ({st.session_state.currency})", f"{st.session_state.currency} {current_price:,.2f}", help=t("Current market price"))
                col3.metric(t("Max Drawdown"), f"{max_drawdown:.2f}%", help=t("Maximum portfolio value drop"))
else:
    st.markdown(
        """
        <div style='text-align: center; margin-top: 50px;'>
            <h1>Welcome to Infi₿it</h1>
            <p style='color: #4A4A4A; font-size: 1.1em;'>{0}</p>
            <p style='color: #4A4A4A'>{1}</p>
        </div>
        """.format(
            t("Monitor your Bitcoin wallet with real-time insights"),
            t("Please login or sign up in the sidebar to access the dashboard.")
        ),
        unsafe_allow_html=True
    )