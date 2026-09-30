import streamlit as st
import pandas as pd
import os
import json
import time
from datetime import datetime
from PIL import Image
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import requests

st.set_page_config(page_title="Balaji CSC Smart Inventory & OCR", layout="centered")

st.title("📦 Balaji CSC Smart Inventory & OCR")
st.markdown("Scan any stationery item or packaging label to automatically extract details with **High-Precision OCR** and log them to your Google Sheet.")

# ─── Schema for High-Precision OCR & Structured Output ──────────────────────────

class StationeryOCRItem(BaseModel):
    raw_ocr_text: str = Field(
        description="All visible text transcribed verbatim from the packaging, price stickers, barcodes, and labels (e.g., 'Classmate Pulse 180 pgs ₹65', 'MRP Rs. 20.00 incl of all taxes', '0.7 mm blue')."
    )
    item_name: str = Field(
        description="Full, specific product title including model, size, color, or page count (e.g., 'Cello Butterflow Blue Ball Pen', 'Classmate Spiral A4 Notebook 200 Pgs')."
    )
    brand: str = Field(
        description="Brand manufacturer (e.g., Classmate, Cello, Doms, Apsara, Nataraj, Camlin, Flair, Hauser, Faber-Castell, Kores, Kangaroo, Luxor). If unknown, use 'Unknown'."
    )
    category: str = Field(
        description="Product category (e.g., Pen, Notebook, Pencil, Adhesive, Stapler/Punch, Calculator, File/Folder, Art/Craft, CSC Govt Form, Office Supply)."
    )
    quantity_in_pack: str = Field(
        description="Packaging quantity (e.g., 'Single Piece', 'Pack of 5', 'Box of 10', 'Pack of 20')."
    )
    price_estimate: str = Field(
        description="Exact printed MRP (e.g., '₹10', '₹50', '₹120') found in the OCR text, or estimated retail price if not printed."
    )
    short_description: str = Field(
        description="Key specifications (e.g., '0.7mm tip, blue ink, waterproof', '70 GSM, 200 ruled pages, spiral bound', 'Non-toxic, 12 shades')."
    )

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("💡 Balaji Growth Tip")
    st.info("The 3-Second Upsell: When a student buys stationery, always ask: **'PAN card bana liya? College ke baad kaam aayega, main yahan banata hoon.'**")
    
    st.markdown("---")
    st.header("📷 OCR Best Practices")
    st.markdown("""
    * **Avoid Glare:** Angle shiny plastic packets away from direct tube lights.
    * **Capture MRP Label:** If price is on the back barcode sticker, snap the back label.
    * **Clear Focus:** Ensure brand logo & printed text are sharp.
    """)

# ─── API Setup ────────────────────────────────────────────────────────────────

api_key = None
try:
    api_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    pass

if not api_key:
    st.subheader("⚙️ Setup")
    api_key = st.text_input("Enter your Gemini API Key:", type="password", help="Get your free key from Google AI Studio (aistudio.google.com)")
    if not api_key:
        st.warning("Please enter your Gemini API Key above or add it to Streamlit Secrets to enable AI OCR scanning.")

client = None
if api_key:
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"Error initializing AI client: {e}")

# ─── Multi-Photo Capture (Front + Back/MRP Label) ────────────────────────────

tab1, tab2 = st.tabs(["📸 Camera Capture", "📁 Upload Photos"])

primary_img = None
secondary_img = None

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        cam1 = st.camera_input("1. Item Photo (Front / Product)")
        if cam1:
            primary_img = Image.open(cam1)
    with col2:
        cam2 = st.camera_input("2. Label / MRP Photo (Optional)")
        if cam2:
            secondary_img = Image.open(cam2)

with tab2:
    col1, col2 = st.columns(2)
    with col1:
        up1 = st.file_uploader("1. Item Photo (Front)", type=["jpg", "jpeg", "png"], key="up1")
        if up1:
            primary_img = Image.open(up1)
            st.image(primary_img, caption="Item Photo", width=300)
    with col2:
        up2 = st.file_uploader("2. Label / MRP Sticker (Optional)", type=["jpg", "jpeg", "png"], key="up2")
        if up2:
            secondary_img = Image.open(up2)
            st.image(secondary_img, caption="Label / MRP Photo", width=300)

# ─── Processing & OCR Analysis ───────────────────────────────────────────────

if primary_img or secondary_img:
    st.markdown("---")
    quantity_to_add = st.number_input("📦 How many units are you adding to stock?", min_value=1, value=1, step=1)

    images_to_analyze = [img for img in [primary_img, secondary_img] if img is not None]

    if st.button("✨ Run High-Precision OCR & Analyze", type="primary", disabled=(client is None)):
        with st.spinner("🔍 Performing deep OCR scan and reading text from packaging..."):
            ocr_prompt = """
            You are an expert OCR and inventory recognition system specialized in Indian stationery retail packaging (e.g. Cello, Classmate, Doms, Apsara, Nataraj, Camlin, Flair, Hauser, Faber-Castell, Luxor, Kangaro, Kores).

            Perform the following in sequence:
            1. OCR EXTRACTION: Carefully read and transcribe all printed text visible on the item, packaging boxes, blister packs, barcode stickers, and price tags. Look specifically for:
               - Brand names and product sub-brands
               - Printed MRP stamps (e.g., 'MRP Rs. ...', 'Incl. of all taxes', 'M.R.P. ₹...')
               - Pack counts (e.g., 'Pack of 5', '10 Pens Free 1', 'Set of 12 Shades')
               - Physical specs: page count (e.g., 172 pgs, 240 pgs), paper size (A4, Long book), GSM (70 GSM), tip size (0.5mm, 0.7mm, Ball/Gel), ink color (Blue, Black, Red).

            2. STRUCTURED EXTRACTION: Extract the exact details into the structured format. If MRP is found in OCR text, format as '₹XX'.
            """

            success = False
            for attempt in range(3):
                try:
                    contents_payload = images_to_analyze + [ocr_prompt]
                    response = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=contents_payload,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=StationeryOCRItem,
                            temperature=0.1,
                        ),
                    )

                    result_json = json.loads(response.text)
                    st.session_state["scanned_data"] = result_json
                    st.session_state["scanned_qty"] = quantity_to_add
                    st.success("✅ OCR & Item Analysis Complete! Review details below before saving.")
                    success = True
                    break

                except Exception as e:
                    if "503" in str(e) and attempt < 2:
                        st.warning(f"Google servers are busy (Attempt {attempt + 1}/3). Retrying OCR in 3 seconds...")
                        time.sleep(3)
                    else:
                        st.error(f"OCR Scan failed: {e}")
                        break

# ─── Editable Confirmation & Save to Google Sheets ───────────────────────────

if "scanned_data" in st.session_state:
    data = st.session_state["scanned_data"]
    qty = st.session_state.get("scanned_qty", 1)

    st.markdown("### 📝 Review & Edit Before Saving")
    
    with st.expander("🔍 View Raw OCR Text Detected on Package", expanded=False):
        st.info(data.get("raw_ocr_text", "No raw text recorded."))

    with st.form("confirm_inventory_form"):
        col1, col2 = st.columns(2)
        with col1:
            edit_name = st.text_input("Item Name", value=data.get("item_name", ""))
            edit_brand = st.text_input("Brand", value=data.get("brand", ""))
            edit_category = st.text_input("Category", value=data.get("category", ""))
        with col2:
            edit_qty = st.number_input("Quantity Added", value=int(qty), min_value=1, step=1)
            edit_pack = st.text_input("Pack Size", value=data.get("quantity_in_pack", ""))
            edit_price = st.text_input("Price / MRP", value=data.get("price_estimate", ""))

        edit_desc = st.text_input("Description / Specs", value=data.get("short_description", ""))

        save_btn = st.form_submit_button("💾 Confirm & Save to Google Sheets", type="primary")

        if save_btn:
            form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfEKrFyFCMDc28A9fNlzoaQwT55ar7h6EsP4TMj5497BMWK-g/formResponse"
            form_data = {
                "entry.1048584284": edit_name,
                "entry.1539118968": edit_brand,
                "entry.1164511249": edit_category,
                "entry.60721169": edit_qty,
                "entry.1355037108": edit_pack,
                "entry.1367724986": edit_price,
                "entry.1644742150": edit_desc
            }

            try:
                res = requests.post(form_url, data=form_data)
                if res.status_code == 200:
                    st.success(f"☁️ Saved **{edit_qty}x '{edit_name}'** ({edit_price}) directly to your Google Sheet!")
                    st.balloons()
                    # Clear session state so next item can be scanned
                    del st.session_state["scanned_data"]
                else:
                    st.error(f"Failed to save to Google Sheets (Status: {res.status_code})")
            except Exception as ex:
                st.error(f"Network error submitting to Google Form: {ex}")