# =======================================================================
# 360 Flower Shop – Order Manager (Stable Full App)
# =======================================================================

import os
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, date
from typing import Optional

import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------
#  DATABASE SETUP (works locally & on Streamlit Cloud)
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
    def ensure_schema(conn):
    """Create table if needed and add any missing columns (safe to run every start)."""
    # Create table if it doesn't exist
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

    # Columns we expect: {name: "TYPE DEFAULT ..."} (SQLite ignores DEFAULT if omitted on ALTER)
    required = {
        "order_no": "TEXT",
        "order_dt": "TEXT",
        "source": "TEXT",
        "customer": "TEXT",
        "vendor": "TEXT",
        "total": "REAL",
        "vendor_price": "REAL",
        "approved_price": "REAL",
        "approval_status": "TEXT",
        "approval_notes": "TEXT",
        "approved_by_shop_ts": "TEXT",
        "approved_by_vendor_ts": "TEXT",
        "commission_pct": "REAL",
        "delivery_dt": "TEXT",
        "delivery_type": "TEXT",
        "status": "TEXT",
        "created_at": "TEXT",
    }

    # Current columns
    cur_cols = {row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}

    # Add any missing columns
    for col, coltype in required.items():
        if col not in cur_cols:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {coltype};")
    conn.commit()

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
    """Seed sample orders if DB is empty."""
    try:
        n = conn.execute("SELECT COUNT(1) FROM orders").fetchone()[0]
    except sqlite3.OperationalError:
        n = 0
    if n > 0:
        return

    now = datetime.utcnow().isoformat(timespec="seconds")
    rows = [
        {
            "order_no": "ORD-202511-0001",
            "order_dt": "2025-11-02",
            "source": "Phone",
            "customer": "Sarah James",
            "vendor": None,
            "total": 85.00,
            "vendor_price": 0.0,
            "approved_price": 0.0,
            "approval_status": "Approved",
            "approval_notes": "",
            "approved_by_shop_ts": now,
            "approved_by_vendor_ts": None,
            "commission_pct": 0.0,
            "delivery_dt": "2025-11-02",
            "delivery_type": "In-Store Pickup",
            "status": "Open",
            "created_at": now,
        },
        {
            "order_no": "ORD-202511-0002",
            "order_dt": "2025-11-02",
            "source": "BloomNet",
            "customer": "BN#1234",
            "vendor": "BloomNet",
            "total": 92.50,
            "vendor_price": 87.50,
            "approved_price": 87.50,
            "approval_status": "Approved",
            "approval_notes": "Vendor confirmed",
            "approved_by_shop_ts": now,
            "approved_by_vendor_ts": now,
            "commission_pct": 0.0,
            "delivery_dt": "2025-11-03",
            "delivery_type": "Vendor Delivery",
            "status": "Vendor Pending",
            "created_at": now,
        },
        {
            "order_no": "ORD-202511-0003",
            "order_dt": "2025-11-01",
            "source": "Teleflora",
            "customer": "TF#8890",
            "vendor": "Teleflora",
            "total": 110.00,
            "vendor_price": 100.00,
            "approved_price": 98.00,
            "approval_status": "Pending",
            "approval_notes": "Negotiation in progress",
            "approved_by_shop_ts": None,
            "approved_by_vendor_ts": now,
            "commission_pct": 0.0,
            "delivery_dt": "2025-11-02",
            "delivery_type": "Vendor Delivery",
            "status": "Vendor Pending",
            "created_at": now,
        },
    ]

    conn.executemany(
        """
        INSERT OR IGNORE INTO orders (
            order_no, order_dt, source, customer, vendor, total,
            vendor_price, approved_price, approval_status, approval_notes,
            approved_by_shop_ts, approved_by_vendor_ts, commission_pct,
            delivery_dt, delivery_type, status, created_at
        )
        VALUES (
            :order_no, :order_dt, :source, :customer, :vendor, :total,
            :vendor_price, :approved_price, :approval_status, :approval_notes,
            :approved_by_shop_ts, :approved_by_vendor_ts, :commission_pct,
            :delivery_dt, :delivery_type, :status, :created_at
        )
        """,
        rows,
    )
    conn.commit()


conn = get_conn()
ensure_schema(conn)       # <-- add this line
seed_demo_data(conn)


# -----------------------------------------------------------------------
#  HELPERS
# -----------------------------------------------------------------------
def next_order_number(conn) -> str:
    """Return next ID like ORD-YYYYMM-0001; guaranteed unique."""
    yyyymm = datetime.now().strftime("%Y%m")
    prefix = f"ORD-{yyyymm}-"
    row = conn.execute(
        "SELECT order_no FROM orders WHERE order_no LIKE ? "
        "ORDER BY order_no DESC LIMIT 1",
        (prefix + "%",)
    ).fetchone()
    last = 0
    if row and row[0]:
        try:
            last = int(row[0].split("-")[-1])
        except Exception:
            last = 0
    while True:
        last += 1
        candidate = f"{prefix}{last:04d}"
        exists = conn.execute("SELECT 1 FROM orders WHERE order_no=? LIMIT 1", (candidate,)).fetchone()
        if not exists:
            return candidate


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
    return "Approved" if abs(vp - ap) < 0.01 else "Pending"


def import_orders_from_df(conn, df: pd.DataFrame, vendor_override: Optional[str] = None):
    """Bulk import orders from a DataFrame."""
    imported = 0
    skipped = 0
    now_iso = datetime.utcnow().isoformat(timespec="seconds")
    need_cols = ["order_no","order_dt","source","customer","vendor","total",
                 "vendor_price","approved_price","approval_status","approval_notes",
                 "delivery_dt","delivery_type","status"]
    for c in need_cols:
        if c not in df.columns:
            df[c] = None
    for _, r in df.iterrows():
        try:
            rec = {
                "order_no": str(r.get("order_no") or "").strip() or next_order_number(conn),
                "order_dt": str(r.get("order_dt") or date.today().isoformat()),
                "source": str(r.get("source") or vendor_override or "-"),
                "customer": str(r.get("customer") or "Vendor Import"),
                "vendor": str(vendor_override or r.get("vendor") or None) or None,
                "total": float(r.get("total") or 0.0),
                "vendor_price": float(r.get("vendor_price") or 0.0),
                "approved_price": float(r.get("approved_price") or 0.0),
                "approval_status": str(r.get("approval_status") or "Pending"),
                "approval_notes": str(r.get("approval_notes") or ""),
                "approved_by_shop_ts": now_iso if str(r.get("approval_status")).strip() == "Approved" else None,
                "approved_by_vendor_ts": now_iso if str(r.get("approval_status")).strip() == "Approved" else None,
                "commission_pct": 0.0,
                "delivery_dt": str(r.get("delivery_dt") or date.today().isoformat()),
                "delivery_type": str(r.get("delivery_type") or "Vendor Delivery"),
                "status": str(r.get("status") or "Vendor Pending"),
                "created_at": now_iso
            }
            insert_order(conn, rec)
            imported += 1
        except sqlite3.IntegrityError:
            skipped += 1
        except Exception:
            skipped += 1
    return imported, skipped

# -----------------------------------------------------------------------
#  UI CONFIG / STYLING
# -----------------------------------------------------------------------
st.set_page_config(page_title="360 Flower Shop – Order Manager", page_icon="🌸", layout="wide")
PINK = "#fed5d3"
st.markdown(f"""
<style>
.stApp {{background-color:{PINK};}}
.tn-card {{background:#fff;border-radius:14px;padding:18px;
box-shadow:0 2px 8px rgba(0,0,0,0.07);border:1px solid rgba(0,0,0,0.06);}}
.tn-badge {{border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600;display:inline-block;}}
.tn-approve{{background:#e6fff3;color:#05603a;border:1px solid #a4e5c2;}}
.tn-pending{{background:#fff9e6;color:#7a4d00;border:1px solid #ffe08a;}}
.tn-dispute{{background:#ffe9ea;color:#8b1c21;border:1px solid #ffb3b6;}}
.tn-total{{font-size:22px;font-weight:700;}}
footer {{visibility:hidden;}}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------
#  SIDEBAR NAVIGATION
# -----------------------------------------------------------------------
st.sidebar.header("TrueNorth Navigation")
page = st.sidebar.radio("Go to", ["🧾 New Order Entry", "📦 Inventory",
                                  "💰 Reconciliation Dashboard", "⚙️ Settings"])

# -----------------------------------------------------------------------
#  PAGE: NEW ORDER ENTRY
# -----------------------------------------------------------------------
if page.startswith("🧾"):
    st.title("New Order Entry")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)

    c0, c1, c2 = st.columns([1.2, 1, 1])
    with c0:
        order_dt = st.date_input("Order Date", value=date.today())
        source = st.selectbox("Order Source", ["In-Store","Phone","BloomNet","Teleflora","Event"])
        customer = st.text_input("Customer Name / External Order ID", placeholder="e.g., Sarah James or BN#1234")
    with c1:
        vendor = st.selectbox("Vendor", ["-","BloomNet","Teleflora"])
        delivery_dt = st.date_input("Delivery Date", value=date.today())
        delivery_type = st.selectbox("Delivery Type", ["In-Store Pickup","Local Delivery","Event"])
    with c2:
        status = st.selectbox("Fulfillment Status", ["Open","Vendor Pending","Vendor Paid","Cancelled"])
        auto_no = st.checkbox("Auto-generate order number", value=True)
        order_no = next_order_number(conn) if auto_no else st.text_input("Order No (unique)").strip()
        st.text_input("Generated Order No", value=order_no, disabled=True)

    st.markdown("---")

    # Quick buttons
    st.subheader("Items (Quick Add)")
    q1, q2, q3, q4 = st.columns(4)
    if q1.button("🌹 Dozen Roses ($85)"): st.session_state.setdefault("cart", []).append({"item":"Dozen Roses","price":85})
    if q2.button("💐 Wrapped Bouquet ($45)"): st.session_state.cart.append({"item":"Wrapped Bouquet","price":45})
    if q3.button("🏺 Standard Vase ($65)"): st.session_state.cart.append({"item":"Standard Vase","price":65})
    if q4.button("🎈 Add-on Balloon ($6)"): st.session_state.cart.append({"item":"Balloon Add-on","price":6})

    desc = st.text_input("Custom Request", placeholder="e.g., Sympathy arrangement with lilies")
    price = st.number_input("Price ($)", min_value=0.0, step=0.5)
    if st.button("➕ Add Custom Line") and desc and price:
        st.session_state.cart.append({"item":desc,"price":float(price)})

    total = round(sum(i["price"] for i in st.session_state.get("cart", [])), 2)
    st.markdown(f"**Calculated Total:** <span class='tn-total'>${total:.2f}</span>", unsafe_allow_html=True)
    total_override = st.number_input("Override Total ($)", min_value=0.0, step=0.01, value=float(total))

    st.markdown("---")
    st.subheader("Price Approval (for BloomNet/Teleflora)")
    a,b,c = st.columns(3)
    vendor_price = a.number_input("Vendor Quoted Price ($)", min_value=0.0, step=0.01)
    approved_price = b.number_input("Shop-Approved Price ($)", min_value=0.0, step=0.01)
    approval_status = c.selectbox("Approval Status", ["Pending","Approved","Disputed"],
                                  index=["Pending","Approved","Disputed"].index(auto_approval(vendor_price, approved_price)))
    approval_notes = st.text_area("Approval Notes")

    if st.button("💾 Save Order"):
        now = datetime.utcnow().isoformat(timespec="seconds")
        record = dict(
            order_no=order_no,
            order_dt=order_dt.isoformat(),
            source=source,
            customer=customer,
            vendor=None if vendor=="-" else vendor,
            total=float(total_override),
            vendor_price=float(vendor_price),
            approved_price=float(approved_price),
            approval_status=approval_status,
            approval_notes=approval_notes,
            approved_by_shop_ts=now if approval_status!="Pending" else None,
            approved_by_vendor_ts=None,
            commission_pct=0.0,
            delivery_dt=delivery_dt.isoformat(),
            delivery_type=delivery_type,
            status=status,
            created_at=now
        )
        try:
            insert_order(conn, record)
            st.session_state["cart"] = []
            st.success(f"✅ Order {order_no} saved.")
        except sqlite3.IntegrityError:
            st.error("❌ Duplicate order number.")
    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------
#  PAGE: INVENTORY (placeholder)
# -----------------------------------------------------------------------
elif page.startswith("📦"):
    st.title("Inventory")
    st.markdown('<div class="tn-card">Inventory tracking coming soon.</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------
#  PAGE: RECONCILIATION DASHBOARD
# -----------------------------------------------------------------------
elif page.startswith("💰"):
    st.title("Reconciliation Dashboard")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)
    f1,f2,f3,f4,f5,f6 = st.columns(6)
    f_source = f1.selectbox("Source",["All","In-Store","Phone","BloomNet","Teleflora","Event"])
    f_vendor = f2.selectbox("Vendor",["All","-","BloomNet","Teleflora"])
    f_status = f3.selectbox("Fulfillment",["All","Open","Vendor Pending","Vendor Paid","Cancelled"])
    f_approval = f4.selectbox("Approval",["All","Pending","Approved","Disputed"])
    start = f5.date_input("Start")
    end = f6.date_input("End")
    st.markdown('</div>', unsafe_allow_html=True)

    df = fetch_orders(conn, f_source, None if f_vendor=="-" else f_vendor, f_status, f_approval, start, end)
    if df.empty:
        st.info("No matching orders found.")
    else:
        def badge(s):
            cls = {"Approved":"tn-approve","Disputed":"tn-dispute"}.get(s,"tn-pending")
            return f"<span class='tn-badge {cls}'>{s}</span>"
        df_display = df.copy()
        df_display["approval_status"] = df_display["approval_status"].apply(badge)
        st.markdown('<div class="tn-card">', unsafe_allow_html=True)
        st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.download_button("⬇️ Export CSV", df.to_csv(index=False).encode("utf-8"),
                           file_name=f"orders_{datetime.now():%Y%m%d_%H%M%S}.csv")

    # --- Import tools
    with st.expander("📥 Import orders from CSV"):
        st.caption("Use the bundled sample (sample.csv) or upload your own with the same columns.")
        cA, cB = st.columns([1, 2])

        with cA:
            if st.button("Load bundled sample.csv"):
                try:
                    sample_path = Path(__file__).parent / "sample.csv"
                    sdf = pd.read_csv(sample_path)
                    imp, skip = import_orders_from_df(conn, sdf)
                    st.success(f"Imported {imp} rows • Skipped {skip}")
                except FileNotFoundError:
                    st.error("sample.csv not found in the app folder.")
                except Exception as e:
                    st.error(f"Import error: {e}")

        with cB:
            up = st.file_uploader("Upload CSV", type=["csv"], key="any_csv")
            vendor_override = st.selectbox("(Optional) Force Vendor for all rows",
                                           ["(none)", "BloomNet", "Teleflora"])
            if up is not None:
                try:
                    udf = pd.read_csv(up)
                    st.dataframe(udf.head(10), use_container_width=True)
                    if st.button("Import uploaded CSV"):
                        vo = None if vendor_override == "(none)" else vendor_override
                        imp, skip = import_orders_from_df(conn, udf, vendor_override=vo)
                        st.success(f"Imported {imp} rows • Skipped {skip}")
                except Exception as e:
                    st.error(f"Upload error: {e}")

# -----------------------------------------------------------------------
#  PAGE: SETTINGS
# -----------------------------------------------------------------------
elif page.startswith("⚙️"):
    st.title("Settings")
    st.markdown('<div class="tn-card">', unsafe_allow_html=True)
    st.text_input("Business Name", "360 Flower Shop")
    st.text_input("Brand Color (hex)", PINK)
    st.checkbox("Enable incoming-call auto-fill (future feature)", value=False)
    st.button("💾 Save Settings")
    st.markdown('</div>', unsafe_allow_html=True)
