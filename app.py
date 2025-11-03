# =======================================================================
# 360 Flower Shop – Order Manager
# Complete Streamlit App (ready for Streamlit Cloud)
# =======================================================================

import os
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------
#  DB SETUP (works locally and on Streamlit Cloud)
# -----------------------------------------------------------------------
IS_CLOUD = os.environ.get("STREAMLIT_RUNTIME", "") != ""
DATA_DIR = Path("/mount/data") if IS_CLOUD else Path(__file__).parent
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "tn_ops.db"
OLD_DB_PATH = Path(__file__).parent / "tn_ops.db"
if not DB_PATH.exists() and OLD_DB_PATH.exists():
    try:
        shutil.copy2(OLD_DB_PATH, DB_PATH)
    except Exception:
        pass


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE,
            order_dt TEXT,
            source TEXT,
            customer TEXT,
            vendor TEXT,
            total REAL,
            vendor_price REAL,
            approved_price REAL,
            approval_status TEXT,
            approval_notes TEXT,
            approved_by_shop_ts TEXT,
            approved_by_vendor_ts TEXT,
            commission_pct REAL,
            delivery_dt TEXT,
            delivery_type TEXT,
            status TEXT DEFAULT 'Open',
            created_at TEXT
        );
    """)
    conn.commit()
    return conn


def seed_demo_data(conn):
    cur = conn.execute("SELECT COUNT(1) FROM orders")
    n = cur.fetchone()[0]
    if n == 0:
        now = datetime.utcnow().isoformat(timespec="seconds")
        demo = [
            ("ORD-202511-0001", "2025-11-02", "Phone", "Sarah James", None, 85.00, 0, 0,
             "Approved", "", now, None, 0, "2025-11-02", "In-Store Pickup", "Open", now),
            ("ORD-202511-0002", "2025-11-02", "BloomNet", "BN#1234", "BloomNet", 92.50, 87.50, 87.50,
             "Approved", "Vendor confirmed", now, now, 0, "2025-11-03", "Vendor Delivery", "Vendor Pending", now),
            ("ORD-202511-0003", "2025-11-01", "Teleflora", "TF#8890", "Teleflora", 110.00, 100.00, 98.00,
             "Pending", "Negotiation in progress", None, now, 0, "2025-11-02", "Vendor Delivery", "Vendor Pending", now),
        ]
        conn.executemany("""
            INSERT OR IGNORE INTO orders
            (order_no, order_dt, source, customer, vendor, total,
             vendor_price, approved_price, approval_status, approval_notes,
             approved_by_shop_ts, approved_by_vendor_ts, commission_pct,
             delivery_dt, delivery_type, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, demo)
        conn.commit()


conn = get_conn()
seed_demo_data(conn)

# -----------------------------------------------------------------------
#  BASIC FUNCTIONS
# -----------------------------------------------------------------------
def next_order_number(conn) -> str:
    yyyymm = datetime.now().strftime("%Y%m")
    prefix = f"ORD-{yyyymm}-"
    row = conn.execute(
        "SELECT order_no FROM orders WHERE order_no LIKE ? ORDER BY order_no DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    if row:
        last = int(row[0].split("-")[-1])
        return f"{prefix}{last+1:04d}"
    return f"{prefix}0001"


def insert_order(conn, record: dict):
    cols = ",".join(record.keys())
    q = ",".join("?" for _ in record)
    conn.execute(f"INSERT INTO orders ({cols}) VALUES ({q})", tuple(record.values()))
    conn.commit()


def fetch_orders(conn, source=None, vendor=None, status=None, approval=None, start=None, end=None):
    sql = """SELECT order_no, order_dt, source, customer, vendor, total,
                    vendor_price, approved_price, approval_status, approval_notes,
                    delivery_dt, delivery_type, status
             FROM orders WHERE 1=1"""
    params = []
    if source and source != "All":   sql += " AND source=?"; params.append(source)
    if vendor and vendor != "All":   sql += " AND vendor=?"; params.append(vendor)
    if status and status != "All":   sql += " AND status=?"; params.append(status)
    if approval and approval != "All": sql += " AND approval_status=?"; params.append(approval)
    if start: sql += " AND date(order_dt)>=date(?)"; params.append(start.isoformat())
    if end:   sql += " AND date(order_dt)<=date(?)"; params.append(end.isoformat())
    sql += " ORDER BY date(order_dt) DESC, order_no DESC"
    return pd.read_sql_query(sql, conn, params=params)


def auto_approval(vendor_price, approved_price):
    try:
        vp = float(vendor_price)
        ap = float(approved_price)
    except Exception:
        return "Pending"
    if abs(vp - ap) < 0.01:
        return "Approved"
    return "Pending"

# -----------------------------------------------------------------------
#  UI SETUP / STYLING
# -----------------------------------------------------------------------
st.set_page_config(page_title="360 Flower Shop - Order Manager", page_icon="🌸", layout="wide")

PINK = "#fed5d3"
CUSTOM_CSS = f"""
<style>
.stApp {{ background-color: {PINK}; }}
.tn-card {{
    background: #ffffff; border-radius: 14px; padding: 18px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.07); border: 1px solid rgba(0,0,0,0.06);
}}
.tn-badge {{
    border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 600; display:inline-block;
}}
.tn-approve {{ background:#e6fff3; color:#05603a; border:1px solid #a4e5c2; }}
.tn-pending {{ background:#fff9e6; color:#7a4d00; border:1px solid #ffe08a; }}
.tn-dispute {{ background:#ffe9ea; color:#8b1c21; border:1px solid #ffb3b6; }}
.tn-total {{ font-size: 22px; font-weight: 700; }}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# -----------------------------------------------------------------------
#  SIDEBAR NAVIGATION
# -----------------------------------------------------------------------
st.sidebar.header("TrueNorth Navigation")
page = st.sidebar.radio(
    "Go to",
    ["🧾 New Order Entry", "📦 Inventory", "💰 Reconciliation Dashboard", "⚙️ Settings"]
)

# -----------------------------------------------------------------------
#  SESSION STATE (for quick order cart)
# -----------------------------------------------------------------------
if "cart" not in st.session_state:
    st.session_state.cart = []


def add_item(name, price):
    st.session_state.cart.append({"item": name, "price": round(float(price), 2)})


def remove_item(i):
    try:
        st.session_state.cart.pop(i)
    except Exception:
        pass


def cart_total():
    return round(sum(i["price"] for i in st.session_state.cart), 2)


# -----------------------------------------------------------------------
#  PAGE: NEW ORDER ENTRY
# -----------------------------------------------------------------------
if page == "🧾 New Order Entry":
    st.title("New Order Entry")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)

    c0, c1, c2 = st.columns([1.2, 1, 1])
    with c0:
        order_dt = st.date_input("Order Date", value=date.today())
        source = st.selectbox("Order Source", ["In-Store", "Phone", "BloomNet", "Teleflora", "Event"])
        customer = st.text_input("Customer Name / External Order ID", placeholder="e.g., Sarah James or BN#1234")
    with c1:
        vendor = st.selectbox("Vendor", ["-", "BloomNet", "Teleflora"])
        delivery_dt = st.date_input("Delivery Date", value=date.today())
        delivery_type = st.selectbox("Delivery Type", ["In-Store Pickup", "Local Delivery", "Event"])
    with c2:
        status = st.selectbox("Fulfillment Status", ["Open", "Vendor Pending", "Vendor Paid", "Cancelled"])
        auto_no = st.checkbox("Auto-generate order number", value=True)
        if auto_no:
            order_no = next_order_number(conn)
            st.text_input("Order No", value=order_no, disabled=True)
        else:
            order_no = st.text_input("Order No (unique)").strip()

    st.markdown("---")

    # Quick buttons
    st.subheader("Items (Quick Add)")
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        if st.button("🌹 Dozen Roses ($85)"): add_item("Dozen Roses", 85)
    with q2:
        if st.button("💐 Wrapped Bouquet ($45)"): add_item("Wrapped Bouquet", 45)
    with q3:
        if st.button("🏺 Standard Vase Arrangement ($65)"): add_item("Standard Vase Arrangement", 65)
    with q4:
        if st.button("🎈 Add-on: Balloon ($6)"): add_item("Balloon Add-on", 6)

    cc1, cc2, cc3 = st.columns([2, 1, 0.6])
    with cc1:
        desc = st.text_input("Custom request", placeholder="e.g., Sympathy arrangement with lilies")
    with cc2:
        price = st.number_input("Price ($)", min_value=0.0, step=0.50, value=0.00)
    with cc3:
        if st.button("➕ Add custom line"):
            if desc and price > 0:
                add_item(desc, price)
            else:
                st.warning("Add a description and price > 0.")

    if st.session_state.cart:
        st.markdown("#### Order Items")
        for i, item in enumerate(st.session_state.cart):
            c = st.columns([6, 2, 1])
            c[0].markdown(f"- {item['item']}")
            c[1].markdown(f"${item['price']:.2f}")
            if c[2].button("🗑️", key=f"rm{i}"):
                remove_item(i)
                st.experimental_rerun()

    calc_total = cart_total()
    st.markdown("---")
    st.markdown(f"**Calculated Total:** <span class='tn-total'>${calc_total:.2f}</span>", unsafe_allow_html=True)
    total_override = st.number_input("Override Total ($)", min_value=float(0.0), step=float(0.01), value=float(calc_total))

    st.markdown("#### Price Approval (for BloomNet/Teleflora)")
    a, b, c = st.columns(3)
    with a:
        vendor_price = st.number_input("Vendor Quoted Price ($)", min_value=0.0, step=0.01, value=0.00)
    with b:
        approved_price = st.number_input("Shop-Approved Price ($)", min_value=0.0, step=0.01, value=0.00)
    with c:
        default_approval = auto_approval(vendor_price, approved_price)
        approval_status = st.selectbox("Approval Status", ["Pending", "Approved", "Disputed"],
                                       index=["Pending", "Approved", "Disputed"].index(default_approval))
    approval_notes = st.text_area("Approval Notes")

    if st.button("💾 Save Order"):
        now = datetime.utcnow().isoformat(timespec="seconds")
        try:
            insert_order(conn, {
                "order_no": order_no,
                "order_dt": order_dt.isoformat(),
                "source": source,
                "customer": customer,
                "vendor": vendor if vendor != "-" else None,
                "total": float(total_override),
                "vendor_price": float(vendor_price),
                "approved_price": float(approved_price),
                "approval_status": approval_status,
                "approval_notes": approval_notes,
                "approved_by_shop_ts": now if approval_status in ("Approved", "Disputed") else None,
                "approved_by_vendor_ts": None,
                "commission_pct": 0.0,
                "delivery_dt": delivery_dt.isoformat(),
                "delivery_type": delivery_type,
                "status": status,
                "created_at": now
            })
            st.session_state.cart = []
            st.success(f"Order {order_no} saved.")
        except sqlite3.IntegrityError:
            st.error("That order number already exists. Try again.")

    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------
#  PAGE: INVENTORY (placeholder)
# -----------------------------------------------------------------------
elif page == "📦 Inventory":
    st.title("Inventory")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)
    st.info("Inventory tracking coming soon.")
    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------
#  PAGE: RECONCILIATION DASHBOARD
# -----------------------------------------------------------------------
elif page == "💰 Reconciliation Dashboard":
    st.title("Reconciliation Dashboard")

    st.markdown('<div class="tn-card">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: f_source = st.selectbox("Source", ["All", "In-Store", "Phone", "BloomNet", "Teleflora", "Event"])
    with c2: f_vendor = st.selectbox("Vendor", ["All", "-", "BloomNet", "Teleflora"])
    with c3: f_status = st.selectbox("Fulfillment", ["All", "Open", "Vendor Pending", "Vendor Paid", "Cancelled"])
    with c4: f_approval = st.selectbox("Approval", ["All", "Pending", "Approved", "Disputed"])
    with c5: start = st.date_input("Start", value=None)
    with c6: end = st.date_input("End", value=None)
    st.markdown('</div>', unsafe_allow_html=True)

    df = fetch_orders(conn, f_source, None if f_vendor == "-" else f_vendor, f_status, f_approval, start, end)

    if not df.empty:
        def badge(s):
            if s == "Approved": return f'<span class="tn-badge tn-approve">{s}</span>'
            if s == "Disputed": return f'<span class="tn-badge tn-dispute">{s}</span>'
            return f'<span class="tn-badge tn-pending">{s}</span>'
        df_display = df.copy()
        df_display["approval_status"] = df_display["approval_status"].apply(badge)
        st.markdown('<div class="tn-card">', unsafe_allow_html=True)
        st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.download_button("⬇️ Export to CSV", df.to_csv(index=False).encode("utf-8"),
                           file_name=f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    else:
        st.info("No matching orders found.")

# -----------------------------------------------------------------------
#  PAGE: SETTINGS
# -----------------------------------------------------------------------
elif page == "⚙️ Settings":
    st.title("Settings")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)
    st.text_input("Business Name", "360 Flower Shop")
    st.text_input("Brand Color (hex)", PINK)
    st.checkbox("Enable incoming-call auto-fill (future feature)", value=False)
    st.button("💾 Save Settings")
    st.markdown('</div>', unsafe_allow_html=True)
