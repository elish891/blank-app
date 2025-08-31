import streamlit as st
import sqlite3
import yfinance as yf

# --- הגדרות בסיסיות ---
DB = "users.db"

# --- פונקציות עזר ---
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_user(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=?", (username,))
    user = cur.fetchone()
    conn.close()
    return user

def update_balance(username, new_balance):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance=? WHERE username=?", (new_balance, username))
    conn.commit()
    conn.close()

def get_holdings(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM holdings WHERE username=?", (username,))
    holdings = cur.fetchall()
    conn.close()
    return holdings

def create_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        balance REAL DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        stock_symbol TEXT,
        quantity INTEGER,
        price REAL
    )
    """)
    conn.commit()
    conn.close()

# --- יצירת טבלאות אם לא קיימות ---
create_tables()

# --- Streamlit App ---
st.title("💹 Simple Stock Trading App")

menu = ["Login", "Register"]
choice = st.sidebar.selectbox("Menu", menu)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

# --- רישום ---
if choice == "Register":
    st.subheader("Create New Account")
    new_user = st.text_input("Username")
    new_pass = st.text_input("Password", type="password")
    if st.button("Register"):
        if new_user and new_pass:
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("INSERT INTO users (username, password, balance) VALUES (?, ?, ?)",
                            (new_user, new_pass, 0))
                conn.commit()
                conn.close()
                st.success("✅ Registration successful! You can login now.")
            except sqlite3.IntegrityError:
                st.error("❌ Username already exists!")
        else:
            st.warning("Enter username and password!")

# --- התחברות ---
if choice == "Login":
    st.subheader("Login to Your Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = get_user(username)
        if user and user["password"] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success(f"✅ Welcome {username}!")
        else:
            st.error("❌ Username or password incorrect!")

# --- דשבורד ---
if st.session_state.logged_in:
    username = st.session_state.username
    user = get_user(username)
    balance = user["balance"]

    st.subheader(f"💰 Balance: ${balance:.2f}")

    # --- Add / Withdraw ---
    st.write("Add / Withdraw Funds")
    col1, col2 = st.columns(2)
    with col1:
        add_amount = st.number_input("Amount to add", min_value=0.0, value=0.0, step=1.0)
        if st.button("Add Funds"):
            balance += add_amount
            update_balance(username, balance)
            st.success(f"✅ Added ${add_amount:.2f}. New balance: ${balance:.2f}")
    with col2:
        withdraw_amount = st.number_input("Amount to withdraw", min_value=0.0, value=0.0, step=1.0)
        if st.button("Withdraw Funds"):
            if withdraw_amount <= balance:
                balance -= withdraw_amount
                update_balance(username, balance)
                st.success(f"✅ Withdrawn ${withdraw_amount:.2f}. New balance: ${balance:.2f}")
            else:
                st.error("❌ Not enough balance!")

    # --- Portfolio ---
    st.subheader("📊 Your Portfolio")
    holdings = get_holdings(username)
    portfolio_data = []
    total_portfolio_value = 0
    for h in holdings:
        symbol = h["stock_symbol"]
        qty = h["quantity"]
        buy_price = h["price"]
        try:
            stock = yf.Ticker(symbol)
            current_price = round(stock.history(period="1d")["Close"].iloc[-1], 2)
            value = round(current_price * qty, 2)
            profit = round((current_price - buy_price) * qty, 2)
            total_portfolio_value += value
        except:
            current_price = value = profit = 0
        portfolio_data.append([symbol, qty, buy_price, current_price, value, profit])
    if portfolio_data:
        st.table(portfolio_data)
        st.write(f"Total Portfolio Value: ${total_portfolio_value:.2f}")
    else:
        st.write("No holdings yet.")

    # --- Trade ---
    st.subheader("📈 Buy / Sell Stocks")
    col1, col2 = st.columns(2)
    with col1:
        trade_symbol = st.text_input("Stock Symbol").upper()
        trade_qty = st.number_input("Quantity", min_value=1, step=1)
    with col2:
        trade_action = st.selectbox("Action", ["buy", "sell"])
        if st.button("Execute Trade"):
            if trade_symbol and trade_qty > 0:
                stock = yf.Ticker(trade_symbol)
                try:
                    current_price = round(stock.history(period="1d")["Close"].iloc[-1], 2)
                except:
                    current_price = 0
                total = round(current_price * trade_qty, 2)
                conn = get_db()
                cur = conn.cursor()
                if trade_action == "buy":
                    if total > balance:
                        st.error("❌ Not enough balance!")
                    else:
                        cur.execute("SELECT id, quantity FROM holdings WHERE username=? AND stock_symbol=? AND price=?",
                                    (username, trade_symbol, current_price))
                        existing = cur.fetchone()
                        if existing:
                            new_qty = existing["quantity"] + trade_qty
                            cur.execute("UPDATE holdings SET quantity=? WHERE id=?", (new_qty, existing["id"]))
                        else:
                            cur.execute("INSERT INTO holdings (username, stock_symbol, quantity, price) VALUES (?, ?, ?, ?)",
                                        (username, trade_symbol, trade_qty, current_price))
                        balance -= total
                        update_balance(username, balance)
                        st.success(f"✅ Bought {trade_qty} shares of {trade_symbol} at ${current_price}")
                elif trade_action == "sell":
                    cur.execute("SELECT id, quantity, price FROM holdings WHERE username=? AND stock_symbol=?",
                                (username, trade_symbol))
                    existing = cur.fetchone()
                    if existing and existing["quantity"] >= trade_qty:
                        total_sell = round(current_price * trade_qty, 2)
                        new_qty = existing["quantity"] - trade_qty
                        if new_qty > 0:
                            cur.execute("UPDATE holdings SET quantity=? WHERE id=?", (new_qty, existing["id"]))
                        else:
                            cur.execute("DELETE FROM holdings WHERE id=?", (existing["id"],))
                        balance += total_sell
                        update_balance(username, balance)
                        st.success(f"✅ Sold {trade_qty} shares of {trade_symbol} at ${current_price}")
                    else:
                        st.error("❌ Not enough shares to sell!")
                conn.commit()
                conn.close()

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.success("Logged out successfully!")
