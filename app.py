# app.py
import sqlite3
from pathlib import Path
from datetime import date, datetime
import pandas as pd
import streamlit as st

# -------------------------------
# Config / Theme
# -------------------------------
st.set_page_config(page_title="TrueNorth Order Hub", layout="wide")
DB_PATH = Path(__file__).with_name("tn_ops.db")
PINK = "#fed5d3"

CUSTOM_CSS = f"""
<style>
    .stApp {{ background: {PINK}; }}
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
    .tn-chip {{ padding:8px 12px; border-radius:12px; border:1px solid rgba(0,0,0,0.1); cursor:pointer; }}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# -------------------------------
# DB Helpers
# -------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
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
            commission_pct REAL,           -- kept for compatibility, not shown in UI
            delivery_dt TEXT,
            delivery_type TEXT,
            status TEXT DEFAULT 'Open',
            created_at TEXT
        );
    """)
    conn.commit()
    return conn

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
    if start:                        sql += " AND date(order_dt)>=date(?)"; params.append(start.isoformat())
    if end:                          sql += " AND date(order_dt)<=date(?)"; params.append(end.isoformat())
    sql += " ORDER BY date(order_dt) DESC, order_no DESC"
    return pd.read_sql_query(sql, conn, params=params)

def auto_approval(vendor_price, approved_price):
    try:
        vp = float(vendor_price) if vendor_price is not None else None
        ap = float(approved_price) if approved_price is not None else None
    except Exception:
        return "Pending"
    if vp is None or ap is None:
        return "Pending"
    return "Approved" if abs(vp - ap) < 0.01 else "Pending"

# -------------------------------
# Sidebar Navigation
# -------------------------------
st.sidebar.header("TrueNorth Navigation")
page = st.sidebar.radio(
    "Go to",
    ["🧾 New Order Entry", "📦 Inventory", "💰 Reconciliation Dashboard", "⚙️ Settings"]
)

conn = get_conn()

# -------------------------------
# Session-state helpers for cart
# -------------------------------
if "cart" not in st.session_state:
    st.session_state.cart = []  # list of dicts: {"item":"Dozen Roses","price":85.00}

def add_item(name, price):
    st.session_state.cart.append({"item": name, "price": round(float(price or 0), 2)})

def remove_item(index):
    try:
        st.session_state.cart.pop(index)
    except Exception:
        pass

def cart_total():
    return round(sum(i["price"] for i in st.session_state.cart), 2)

# -------------------------------
# New Order Entry
# -------------------------------
if page == "🧾 New Order Entry":
    st.title("New Order Entry")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)

    # --- Top row: Order meta ---
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
        # order number
        auto_no = st.checkbox("Auto-generate order number", value=True)
        if auto_no:
            order_no = next_order_number(conn)
            st.text_input("Order No", value=order_no, disabled=True, key="order_no_display")
        else:
            order_no = st.text_input("Order No (must be unique)", placeholder="e.g., ORD-202511-0007").strip()

    st.markdown("---")

    # --- Quick Order buttons + Custom line ---
    st.subheader("Items (Quick Add)")
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        if st.button("🌹 Dozen Roses ($85)"):
            add_item("Dozen Roses", 85)
    with q2:
        if st.button("💐 Wrapped Bouquet ($45)"):
            add_item("Wrapped Bouquet", 45)
    with q3:
        if st.button("🏺 Standard Vase Arrangement ($65)"):
            add_item("Standard Vase Arrangement", 65)
    with q4:
        if st.button("🎈 Add-on: Balloon ($6)"):
            add_item("Balloon Add-on", 6)

    st.caption("Prices are placeholders for demo. We’ll make these configurable in Settings next.")

    # Custom line
    cc1, cc2, cc3 = st.columns([2, 1, 0.6])
    with cc1:
        custom_desc = st.text_input("Custom request description", placeholder="e.g., ‘Sympathy arrangement with lilies’")
    with cc2:
        custom_price = st.number_input("Price ($)", min_value=0.0, step=0.50, value=0.00)
    with cc3:
        if st.button("➕ Add custom line"):
            if custom_desc and custom_price > 0:
                add_item(custom_desc, custom_price)
            else:
                st.warning("Add a description and price > $0.")

    # Cart table
    if st.session_state.cart:
        st.markdown("#### Order Items")
        items_df = pd.DataFrame(st.session_state.cart)
        # Add remove buttons
        for i, row in items_df.iterrows():
            cols = st.columns([6, 2, 1])
            cols[0].markdown(f"- {row['item']}")
            cols[1].markdown(f"${row['price']:.2f}")
            if cols[2].button("🗑️", key=f"rm_{i}"):
                remove_item(i)
                st.experimental_rerun()

    # Calculated total (editable override)
    calc_total = cart_total()
    st.markdown("---")
    tcol1, tcol2 = st.columns([2, 1])
    with tcol1:
        st.markdown(f"**Calculated Total:** <span class='tn-total'>${calc_total:.2f}</span>", unsafe_allow_html=True)
    with tcol2:
        total_override = st.number_input(
    "Override Total ($)",
    min_value=float(0.0),
    step=float(0.01),
    value=float(calc_total)
)

    # --- Price Approval section (for vendor network orders) ---
    st.markdown("#### Price Approval (for BloomNet/Teleflora)")
    a, b, c = st.columns(3)
    with a:
        vendor_price = st.number_input("Vendor Quoted Price ($)", min_value=0.0, step=0.01, value=0.00)
    with b:
        approved_price = st.number_input("Shop-Approved Price ($)", min_value=0.0, step=0.01, value=0.00)
    with c:
        default_approval = auto_approval(vendor_price, approved_price)
        approval_status = st.selectbox("Approval Status", ["Pending", "Approved", "Disputed"],
                                       index=["Pending","Approved","Disputed"].index(default_approval))
    approval_notes = st.text_area("Approval Notes (negotiations, confirmation IDs, etc.)")

    # Save button
    if st.button("💾 Save Order"):
        if not order_no:
            st.error("Please provide an Order Number (or enable auto-generate).")
        else:
            now = datetime.utcnow().isoformat(timespec="seconds")
            try:
                insert_order(conn, {
                    "order_no": order_no,
                    "order_dt": order_dt.isoformat(),
                    "source": source,
                    "customer": customer,
                    "vendor": vendor if vendor != "-" else None,
                    "total": float(total_override),          # store the chosen total
                    "vendor_price": float(vendor_price),
                    "approved_price": float(approved_price),
                    "approval_status": approval_status,
                    "approval_notes": approval_notes,
                    "approved_by_shop_ts": now if approval_status in ("Approved","Disputed") else None,
                    "approved_by_vendor_ts": None,
                    "commission_pct": 0.0,                   # removed from UI
                    "delivery_dt": delivery_dt.isoformat(),
                    "delivery_type": delivery_type,
                    "status": status,
                    "created_at": now
                })
                # Clear cart after save
                st.session_state.cart = []
                st.success(f"Order {order_no} saved.")
            except sqlite3.IntegrityError:
                st.error("That Order Number already exists. Use auto-generate or enter a unique number.")
    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------
# Inventory (placeholder)
# -------------------------------
elif page == "📦 Inventory":
    st.title("Inventory")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)
    st.info("Inventory UI placeholder – coming next: receive stock, quick waste, low-stock alerts, and assemblies.")
    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------
# Reconciliation Dashboard with Vendor Import
# -------------------------------
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

    df = fetch_orders(
        conn,
        source=f_source,
        vendor=None if f_vendor == "-" else f_vendor,
        status=f_status,
        approval=f_approval,
        start=start if start else None,
        end=end if end else None
    )

    if not df.empty:
        def badge(s):
            if s == "Approved": return f'<span class="tn-badge tn-approve">{s}</span>'
            if s == "Disputed": return f'<span class="tn-badge tn-dispute">{s}</span>'
            return f'<span class="tn-badge tn-pending">{s}</span>'
        df_display = df.copy()
        df_display["approval_status"] = df_display["approval_status"].apply(badge)
        st.markdown('<div class="tn-card">', unsafe_allow_html=True)
        st.write(df.shape[0], "orders")
        st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("No orders match your filters.")

    st.download_button(
        "⬇️ Export to CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

    # Vendor Import
    st.markdown("### Vendor Import (BloomNet / Teleflora)")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)
    st.caption("CSV columns expected: `Order Date`, `Customer Name`, `Order Total`, `Vendor Price`, `Approved Price`, `Delivery Date`, `Notes`")
    uploaded = st.file_uploader("Upload CSV", type=["csv"], key="vendor_file")
    vendor_guess = "-"
    if uploaded and ("bloom" in uploaded.name.lower()):
        vendor_guess = "BloomNet"
    elif uploaded and ("tele" in uploaded.name.lower()):
        vendor_guess = "Teleflora"
    vendor = st.selectbox("Vendor", ["BloomNet", "Teleflora", "-"],
                          index=0 if vendor_guess=="BloomNet" else 1 if vendor_guess=="Teleflora" else 2)

    if uploaded:
        try:
            preview = pd.read_csv(uploaded)
            st.dataframe(preview.head(8), use_container_width=True)
            if st.button("📥 Import Orders"):
                imported, skipped = 0, 0
                for _, r in preview.iterrows():
                    try:
                        vp = float(r.get("Vendor Price", 0.0))
                        ap = float(r.get("Approved Price", 0.0))
                        approval_status = "Approved" if abs(vp - ap) < 0.01 else "Pending"
                        now = datetime.utcnow().isoformat(timespec="seconds")
                        order_no = next_order_number(conn)
                        insert_order(conn, {
                            "order_no": order_no,
                            "order_dt": str(r.get("Order Date", date.today())),
                            "source": vendor,
                            "customer": str(r.get("Customer Name", "Vendor Import")),
                            "vendor": vendor if vendor != "-" else None,
                            "total": float(r.get("Order Total", 0.0)),
                            "vendor_price": vp,
                            "approved_price": ap,
                            "approval_status": approval_status,
                            "approval_notes": str(r.get("Notes", "")),
                            "approved_by_shop_ts": now if approval_status=="Approved" else None,
                            "approved_by_vendor_ts": now,
                            "commission_pct": 0.0,
                            "delivery_dt": str(r.get("Delivery Date", date.today())),
                            "delivery_type": "Vendor Delivery",
                            "status": "Vendor Pending",
                            "created_at": now
                        })
                        imported += 1
                    except Exception:
                        skipped += 1
                st.success(f"Imported {imported} orders. Skipped {skipped}.")
        except Exception as e:
            st.error(f"Error reading file: {e}")
    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------
# Settings (placeholder)
# -------------------------------
elif page == "⚙️ Settings":
    st.title("Settings")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)
    st.text_input("Business Name", "Example Flower Shop")
    st.text_input("Brand Color (hex)", PINK)
    st.checkbox("Enable incoming-call auto-fill (requires CID listener)", value=False, help="Future option")
    st.button("💾 Save Settings")
    st.markdown('</div>', unsafe_allow_html=True)
