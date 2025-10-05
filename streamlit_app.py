
import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="ESA Dropshipping Dashboard", layout="wide")

# --- Helpers ---
DEFAULT_API = "https://esa-dropshipping.onrender.com"
API_BASE = st.secrets.get("API_BASE_URL", DEFAULT_API)

st.sidebar.title("🔗 Conexión")
API_BASE = st.sidebar.text_input("API Base URL", API_BASE)
if API_BASE.endswith("/"):
    API_BASE = API_BASE[:-1]

def api_get(path):
    url = f"{API_BASE}{path}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"GET {url} → {e}")
        return None

def api_post(path, payload=None):
    url = f"{API_BASE}{path}"
    try:
        r = requests.post(url, json=payload or {}, timeout=30)
        if r.status_code >= 400:
            st.error(f"POST {url} → {r.status_code}: {r.text}")
        r.raise_for_status()
        if r.text:
            return r.json()
        return {}
    except Exception as e:
        st.error(f"POST {url} → {e}")
        return None

st.sidebar.markdown("**Estado del API:**")
health = api_get("/health")
if health and health.get("status") == "ok":
    st.sidebar.success("Conectado ✅")
else:
    st.sidebar.error("Sin conexión ❌")

st.title("📦 ESA Dropshipping – Dashboard")
st.caption("Control de productos, pedidos y logística (Deliver Fever)")

tab_overview, tab_products, tab_orders, tab_shipping = st.tabs(
    ["📊 Overview", "🛒 Productos", "🧾 Órdenes", "🚚 Envíos"]
)

# --- Overview ---
with tab_overview:
    st.subheader("Resumen")
    # Requiere endpoint GET /orders
    orders = api_get("/orders")
    if orders is None:
        st.info("Aún no existe el endpoint **GET /orders** en tu API. Agrega la función list_orders y vuelve a recargar.")
        st.code(
            'from fastapi import APIRouter, Depends\nfrom sqlalchemy.orm import Session\nfrom ..database import get_db\nfrom .. import models, schemas\n\n@router.get("/", response_model=list[schemas.OrderOut])\ndef list_orders(db: Session = Depends(get_db)):\n    return db.query(models.Order).all()',
            language="python",
        )
    else:
        df_orders = pd.DataFrame(orders)
        if not df_orders.empty:
            col1, col2, col3, col4, col5 = st.columns(5)
            counts = df_orders["status"].value_counts()
            col1.metric("Pending", int(counts.get("pending", 0)))
            col2.metric("Forwarding", int(counts.get("forwarding", 0)))
            col3.metric("At DF", int(counts.get("at_df", 0)))
            col4.metric("En MX", int(counts.get("in_transit_mx", 0)))
            col5.metric("Entregadas", int(counts.get("delivered", 0)))
            st.dataframe(df_orders)
        else:
            st.info("No hay órdenes aún. Crea una en la pestaña **Órdenes**.")

# --- Products ---
with tab_products:
    st.subheader("Productos")
    products = api_get("/products") or []
    st.write(f"Productos cargados: {len(products)}")
    if products:
        st.dataframe(pd.DataFrame(products))

    st.markdown("---")
    st.write("### ➕ Crear producto")
    with st.form("create_product"):
        sku = st.text_input("SKU", "WAL-0001")
        name = st.text_input("Nombre", "Playera básica")
        description = st.text_area("Descripción", "Algodón 100%")
        price_usd = st.number_input("Precio USD", min_value=0.0, value=9.9, step=0.1)
        weight_kg = st.number_input("Peso (kg)", min_value=0.0, value=0.25, step=0.05)
        origin = st.selectbox("Origen", ["US", "MX"])
        submitted = st.form_submit_button("Crear")
        if submitted:
            payload = {
                "sku": sku,
                "name": name,
                "description": description,
                "price_usd": price_usd,
                "weight_kg": weight_kg,
                "origin": origin,
            }
            res = api_post("/products/", payload)
            if res:
                st.success(f"Producto creado: {res.get('id')} – {res.get('name')}")

# --- Orders ---
with tab_orders:
    st.subheader("Órdenes")
    products = api_get("/products") or []
    product_map = {f"[{p['id']}] {p['name']} (SKU {p['sku']})": p["id"] for p in products}

    with st.form("create_order"):
        st.write("### ➕ Crear orden")
        customer_name = st.text_input("Nombre del cliente", "Juan Pérez")
        customer_email = st.text_input("Email del cliente", "juan@example.com")
        ship_to_city = st.text_input("Ciudad destino", "Monterrey")
        ship_to_state = st.text_input("Estado destino", "NL")
        ship_to_zip = st.text_input("CP", "64000")

        if product_map:
            prod_label = st.selectbox("Producto", list(product_map.keys()))
            qty = st.number_input("Cantidad", min_value=1, value=1, step=1)
            items = [{"product_id": product_map[prod_label], "qty": int(qty)}]
        else:
            st.warning("No hay productos. Crea uno en la pestaña Productos.")
            items = []

        submitted = st.form_submit_button("Crear orden")
        if submitted:
            if not items:
                st.error("Agrega al menos un producto.")
            else:
                payload = {
                    "customer_name": customer_name,
                    "customer_email": customer_email,
                    "ship_to_city": ship_to_city,
                    "ship_to_state": ship_to_state,
                    "ship_to_zip": ship_to_zip,
                    "items": items,
                }
                res = api_post("/orders/", payload)
                if res:
                    st.success(f"Orden creada: #{res.get('id')} para {res.get('customer_name')}")

    st.markdown("---")
    st.write("### 📋 Listado de órdenes")
    orders = api_get("/orders")
    if isinstance(orders, list) and orders:
        st.dataframe(pd.DataFrame(orders))
    else:
        st.info("Sin órdenes o falta el endpoint GET /orders.")

# --- Shipping ---
with tab_shipping:
    st.subheader("Envíos (Deliver Fever)")

    st.write("### ➕ Crear envío")
    with st.form("create_shipment"):
        order_id = st.number_input("Order ID", min_value=1, value=1, step=1)
        carrier = st.text_input("Carrier", "DeliverFever")
        tracking = st.text_input("Tracking", "DF-TEST-001")
        dest_city = st.text_input("Ciudad destino", "Monterrey")
        dest_state = st.text_input("Estado destino", "NL")
        submitted = st.form_submit_button("Crear envío")
        if submitted:
            payload = {
                "order_id": int(order_id),
                "carrier": carrier,
                "tracking": tracking,
                "dest_city": dest_city,
                "dest_state": dest_state,
            }
            res = api_post("/shipping/create", payload)
            if res:
                st.success(f"Envío creado: #{res.get('id')} (order {res.get('order_id')})")

    st.markdown("---")
    st.write("### 🔁 Actualizar estatus de envío")
    with st.form("update_status"):
        shipment_id = st.number_input("Shipment ID", min_value=1, value=1, step=1)
        new_status = st.selectbox("Nuevo estatus", ["at_df", "in_transit_mx", "delivered"])
        submitted2 = st.form_submit_button("Actualizar")
        if submitted2:
            path = f"/shipping/{int(shipment_id)}/status/{new_status}"
            res = api_post(path, {})
            if res and res.get("ok"):
                st.success(f"Shipment {int(shipment_id)} → {new_status}")

    st.markdown("---")
    st.write("### 📦 Listado de envíos")
    shipments = api_get("/shipping")  # requiere endpoint GET /shipping
    if isinstance(shipments, list):
        if shipments:
            st.dataframe(pd.DataFrame(shipments))
        else:
            st.info("No hay envíos aún.")
    else:
        st.info("Aún no existe el endpoint **GET /shipping**. Puedes agregarlo así:")
        st.code(
            'from fastapi import APIRouter, Depends\nfrom sqlalchemy.orm import Session\nfrom ..database import get_db\nfrom .. import models\n\n@router.get("/")\ndef list_shipments(db: Session = Depends(get_db)):\n    return db.query(models.Shipment).all()',
            language="python",
        )

st.caption("Hecho con ❤️ por ESA (FastAPI + Streamlit)")
