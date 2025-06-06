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

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Stripe Configuration ---
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_BUY_BUTTON_ID = "buy_btn_1RX6WDP91qk5UbUaXy5ZgtAC"
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

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

# --- User Data Management ---
def load_users():
    try:
        if os.path.exists("users.json"):
            with open("users.json", "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        return {}

def save_users(users):
    try:
        with open("users.json", "w") as f:
            json.dump(users, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving users: {e}")

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
    unsafe_allow_html=True,
)

# --- Sidebar: Sign-Up and Login ---
with st.sidebar:
    st.markdown(
        """
        <hr style='border-color: #E0E0E0; margin: 10px 0;'>
        <h3 style='color: #1A1A1A; font-family: Inter, sans-serif;'>InfiBit Analytics</h3>
        """,
        unsafe_allow_html=True,
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
                        users[new_email] = {
                            "wallet_address": new_wallet,
                            "password_hash": hash_password(new_password),
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        save_users(users)
                        st.success(t("Signed up successfully! Please log in."))
            else:
                st.error(t("Please fill out all fields."))

    # Sidebar Controls (only for logged-in users)
    if st.session_state.user_email:
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
            unsafe_allow_html=True,
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

        # Paywall overlay with Stripe Buy Button
        st.markdown(
            f"""
            <div class='paywall-container'>
                <h2>{t('Subscribe to InfiBit Analytics')}</h2>
                <p>{t('Unlock full access to the Bitcoin Wallet Dashboard with a subscription.')}</p>
                <script async src="https://js.stripe.com/v3/buy-button.js"></script>
                <stripe-buy-button
                    buy-button-id="{STRIPE_BUY_BUTTON_ID}"
                    publishable-key="{STRIPE_PUBLISHABLE_KEY}"
                    client-reference-id="{st.session_state.user_email}"
                >
                </stripe-buy-button>
                <p style='margin-top: 20px; color: #4A4A4A;'>{t('After subscribing, re-login to activate your account.')}</p>
            </div>
            """,
            unsafe_allow_html=True,
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
            unsafe_allow_html=True,
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
                    users = load_users()
                    users[st.session_state.user_email]["wallet_address"] = wallet_input
                    save_users(users)
                    st.success(t("Wallet address updated successfully!"))
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
                            st.warning(t("Showing metrics based on the last 20 transactions. For full accuracy, select 'All' transactions. Will take longer to load."))
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric(t("Bitcoin Balance"), f"{net_btc:.8f} BTC", help=t("Total Bitcoin in your wallet"))
                        col2.metric(f"{t('Current Value')} ({currency})", f"{wallet_value:,.2f}", help=t("Current market value of your Bitcoin"))
                        col3.metric(f"{t('Profit/Loss')} ({currency})", f"{gain:,.2f}", delta=f"{gain_pct:.2f}%", help=t("Unrealized profit or loss"))
                        col4.metric(t("30-Day Volatility"), f"{volatility:.2f}%", help=t("Annualized price volatility of Bitcoin"))

                        col5, col6, col7, col8 = st.columns(4)
                        col5.metric(f"{t('Average Buy Price')} ({currency})", f"{avg_buy:,.2f}", help=t("Average price paid per Bitcoin"))
                        col6.metric(f"{t('Total Invested')} ({currency})", f"{invested:,.2f}", help=t("Total amount invested"))
                        col7.metric(t("Holding Period"), f"{int(holding_period_days)} days", help=t("Time since first transaction"))
                        col8.metric(t("Wallet vs. Market"), f"{gain_pct - btc_return:.2f}%", help=t("Wallet ROI relative to Bitcoin market return"))

                        st.markdown(f"### 📊 {t('Summary Metrics')}")
                        summary_data = pd.DataFrame({
                            t("Metric"): [t("Bitcoin Balance"), t("Current Value"), t("Total Invested"), t("Profit/Loss"), t("ROI"), t("Volatility")],
                            t("Value"): [f"{net_btc:.8f} BTC", f"{wallet_value:,.2f} {currency}", f"{invested:,.2f} {currency}", f"{gain:,.2f} {currency}", f"{gain_pct:.2f}%", f"{volatility:.2f}%"]
                        })
                        st.dataframe(summary_data, use_container_width=True, hide_index=True)

                    # --- Transactions Tab ---
                    with tab2:
                        st.markdown(f"### 📜 {t('Transaction History')}")
                        df_display = df.copy()
                        df_display["Value (" + currency + ")"] = df_display["USD Value"] * multiplier
                        df_display["Price at Tx"] = df_display["Price at Tx"] * multiplier
                        df_display["Date"] = df_display["Date"].dt.strftime("%Y-%m-%d")

                        date_range = st.date_input(
                            t("Filter by Date"),
                            [pd.to_datetime(df_display["Date"]).min(), pd.to_datetime(df_display["Date"]).max()],
                            min_value=pd.to_datetime(df_display["Date"]).min(),
                            max_value=pd.to_datetime(df_display["Date"]).max(),
                            key="date_filter",
                        )

                        filtered_df = df_display[
                            (df_display["Date"] >= str(date_range[0]))
                            & (df_display["Date"] <= str(date_range[1]))
                        ]

                        st.dataframe(
                            filtered_df[["Date", "Type", "BTC", "Price at Tx", "Value (" + currency + ")", "TXID", "Confirmed", "Counterparty"]].sort_values("Date", ascending=False),
                            use_container_width=True,
                            column_config={
                                "Date": t("Date"),
                                "Type": t("Type"),
                                "BTC": t("Amount (BTC)"),
                                "Price at Tx": t(f"Price ({currency})"),
                                "Value (" + currency + ")": t(f"Value ({currency})"),
                                "TXID": t("Transaction ID"),
                                "Confirmed": t("Confirmed"),
                                "Counterparty": t("Counterparty Address"),
                            },
                            hide_index=True,
                        )

                        csv = filtered_df.to_csv(index=False)
                        st.download_button(
                            t("Download Transactions"),
                            csv,
                            "transactions_data.csv",
                            "text/csv",
                            key="download-csv",
                        )

                        st.markdown(f"### 📊 {t('Transaction Volume')}")
                        volume_df = (
                            filtered_df.groupby(["Date", "Type"])["BTC"]
                            .sum()
                            .unstack()
                            .fillna(0)
                            .reset_index()
                        )
                        fig = go.Figure()
                        fig.add_trace(
                            go.Bar(
                                x=volume_df["Date"],
                                y=volume_df.get("IN", pd.Series(0)),
                                name=t("Received"),
                                marker_color="#28A745",
                            )
                        )
                        fig.add_trace(
                            go.Bar(
                                x=volume_df["Date"],
                                y=volume_df.get("OUT", pd.Series(0)) * -1,
                                name=t("Sent"),
                                marker_color="#DC3545",
                            )
                        )
                        fig.update_layout(
                            barmode="relative",
                            title=t("BTC Sent and Received"),
                            xaxis_title=t("Date"),
                            yaxis_title=t("Amount (BTC)"),
                            template="plotly_white",
                            plot_bgcolor="rgba(0,0,0,0)",
                            height=400,
                            font=dict(family="Inter", size=12),
                        )
                        st.plotly_chart(fig, use_container_width=True)

                        st.markdown(f"### 📈 {t('Transaction Frequency')}")
                        freq_df = filtered_df.groupby([pd.to_datetime(filtered_df["Date"]).dt.to_period("M"), "Type"]).size().unstack().fillna(0).reset_index()
                        freq_df["Date"] = freq_df["Date"].apply(lambda x: x.strftime('%Y-%m'))
                        fig = go.Figure()
                        for t_type in ["IN", "OUT"]:
                            fig.add_trace(
                                go.Scatter(
                                    x=freq_df["Date"],
                                    y=freq_df.get(t_type, pd.Series(0)),
                                    name=t("Received" if t_type == "IN" else "Sent"),
                                    line=dict(color="#28A745" if t_type == "IN" else "#DC3545"),
                                    mode="lines+markers",
                                )
                            )
                        fig.update_layout(
                            title=t("Monthly Transaction Count"),
                            xaxis_title=t("Month"),
                            yaxis_title=t("Number of Transactions"),
                            template="plotly_white",
                            plot_bgcolor="rgba(0,0,0,0)",
                            height=400,
                            font=dict(family="Inter", size=12),
                        )
                        st.plotly_chart(fig, use_container_width=True)

                        st.markdown(f"### 📊 {t('Transaction Statistics')}")
                        avg_btc_in = filtered_df[filtered_df["Type"] == "IN"]["BTC"].mean() if not filtered_df[filtered_df["Type"] == "IN"].empty else 0
                        avg_btc_out = filtered_df[filtered_df["Type"] == "OUT"]["BTC"].mean() if not filtered_df[filtered_df["Type"] == "OUT"].empty else 0
                        avg_value_in = filtered_df[filtered_df["Type"] == "IN"]["Value (" + currency + ")"].mean() if not filtered_df[filtered_df["Type"] == "IN"].empty else 0
                        avg_value_out = filtered_df[filtered_df["Type"] == "OUT"]["Value (" + currency + ")"].mean() if not filtered_df[filtered_df["Type"] == "OUT"].empty else 0
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric(t("Avg. Received (BTC)"), f"{avg_btc_in:.8f}", help=t("Average BTC per incoming transaction"))
                        col2.metric(t("Avg. Sent (BTC)"), f"{avg_btc_out:.8f}", help=t("Average BTC per outgoing transaction"))
                        col3.metric(t(f"Avg. Received ({currency})"), f"{avg_value_in:,.2f}", help=t("Average value per incoming transaction"))
                        col4.metric(t(f"Avg. Sent ({currency})"), f"{avg_value_out:,.2f}", help=t("Average value per outgoing transaction"))

                        st.markdown(f"### 🤝 {t('Top Counterparties')}")
                        counterparty_df = filtered_df.groupby("Counterparty")["BTC"].sum().reset_index().sort_values("BTC", ascending=False).head(5)
                        counterparty_df["BTC"] = counterparty_df["BTC"].abs()
                        st.dataframe(
                            counterparty_df,
                            use_container_width=True,
                            column_config={
                                "Counterparty": t("Address"),
                                "BTC": t("Total BTC Transacted"),
                            },
                            hide_index=True,
                        )

                    # --- Portfolio Tab ---
                    with tab3:
                        st.markdown(f"### 📈 {t('Portfolio Performance')}")
                        fig = go.Figure()
                        fig.add_trace(
                            go.Scatter(
                                x=value_df["Date"],
                                y=value_df["Market Value"],
                                name=t("Market Value"),
                                line=dict(color="#007BFF"),
                                fill="tozeroy",
                            )
                        )
                        fig.add_trace(
                            go.Scatter(
                                x=value_df["Date"],
                                y=value_df["Cost Basis"],
                                name=t("Cost Basis"),
                                line=dict(color="#6C757D", dash="dash"),
                            )
                        )
                        fig.update_layout(
                            title=t("Portfolio Value vs. Cost Basis"),
                            xaxis_title=t("Date"),
                            yaxis_title=currency,
                            template="plotly_white",
                            plot_bgcolor="rgba(0,0,0,0)",
                            height=400,
                            font=dict(family="Inter", size=12),
                        )
                        st.plotly_chart(fig, use_container_width=True)

                        st.markdown(f"### 📊 {t('Performance Summary')}")
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric(t("ROI"), f"{gain_pct:.2f}%", help=t("Percentage return based on current value vs. invested amount"))
                        col2.metric(f"{t('Current BTC Price')} ({currency})", f"{current_price:,.2f}", help=t("Latest market price of Bitcoin"))
                        col3.metric(t("Sharpe Ratio"), f"{sharpe_ratio:.2f}", help=t("Risk-adjusted return (annualized)"))
                        col4.metric(t("Max Drawdown"), f"{max_drawdown:.2f}%", help=t("Largest peak-to-trough decline"))

                        st.markdown(f"### 🔮 {t('Portfolio Scenarios')}")
                        scenario_data = []
                        for change in [-20, -10, 0, 10, 20]:
                            scenario_price = current_price * (1 + change / 100)
                            scenario_value = net_btc * scenario_price
                            scenario_data.append({
                                t("BTC Price Change"): f"{change:+.0f}%",
                                t(f"Portfolio Value ({currency})"): f"{scenario_value:,.2f}"
                            })
                        st.dataframe(
                            pd.DataFrame(scenario_data),
                            use_container_width=True,
                            hide_index=True,
                        )

                    # --- Bit Notes Tab ---
                    with tab4:
                        st.markdown(f"### 📝 {t('₿it Notes')}")
                        st.markdown(t("Share your insights on Bitcoin and read notes from other users. Add your Bit Note below!"))

                        with st.form("bit_note_form"):
                            st.subheader(t("Add ₿it Note"))
                            title = st.text_input(t("Title"), max_chars=100)
                            description = st.text_area(t("Description"), max_chars=500)
                            article_text = st.text_area(t("₿it Note Text"), max_chars=1000)
                            submitted = st.form_submit_button(t("Submit ₿it Note"))

                            if submitted:
                                if title and description and article_text:
                                    bit_notes = load_bit_notes()
                                    new_note = {
                                        "title": title,
                                        "description": description,
                                        "article_text": article_text,
                                        "date_posted": datetime.now(timezone.utc).isoformat(),
                                        "author": st.session_state.user_email
                                    }
                                    bit_notes.append(new_note)
                                    save_bit_notes(bit_notes)
                                    st.success(t("Bit Note added successfully!"))
                                else:
                                    st.error(t("Please fill out all fields."))

                        st.markdown(f"### {t('All ₿it Notes')}")
                        bit_notes = load_bit_notes()
                        if bit_notes:
                            bit_notes = sorted(bit_notes, key=lambda x: x["date_posted"], reverse=True)
                            for note in bit_notes:
                                date_posted = datetime.fromisoformat(note["date_posted"]).strftime("%Y-%m-%d %H:%M:%S UTC")
                                with st.expander(f"{t(note['title'])} ({date_posted})"):
                                    st.markdown(
                                        f"""
                                        <div style='padding: 10px; border-bottom: 1px solid #E0E0E0;'>
                                            <h4 style='margin: 5px 0;'>{t(note['title'])}</h4>
                                            <p style='color: #4A4A4A;'>{t(note['description'])}</p>
                                            <p><strong>{t('Notes Text')}:</strong> {t(note['article_text'])}</p>
                                            <p><strong>{t('Posted')}:</strong> {date_posted}</p>
                                            <p><strong>{t('Author')}:</strong> {note.get('author', 'Anonymous')}</p>
                                        </div>
                                        """,
                                        unsafe_allow_html=True,
                                    )
                        else:
                            st.info(t("No ₿it Notes available yet. Be the first to add one!"))
        else:
            st.info(t("Please enter a valid Bitcoin wallet address to view the dashboard."))
else:
    st.info(t("Please log in or sign up to access the dashboard."))

# --- Footer ---
st.markdown(
    """
    <div style='text-align: center; margin-top: 40px; padding: 20px; background-color: #F5F6F5; border-radius: 8px;'>
        <hr style='border-color: #E0E0E0; margin: 20px 0;'>
            <p style='color: #4A4A4A; font-size: 0.9em;'>
                © <p style='color: #4A4A4A; font-size: 14px; margin: 0px'>© 2025 Infi₿it Analytics</p>
            </p>
        </div>
    """,
    unsafe_html=True,
    unsafe_allow_html=True
)