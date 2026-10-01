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

st.set_page_config(page_title="Balaji CSC Smart Inventory", layout="centered")

st.title("📦 Balaji CSC Smart Inventory")
st.markdown("Take or upload a photo of any stationery item to automatically log it into your **`Photo Inventory V1`** Google Sheet.")

# ─── Schema for Item Recognition ─────────────────────────────────────────────

class InventoryItem(BaseModel):
    item_name: str = Field(description="Product title (e.g., Cello Gripper Blue Ball Pen, Classmate A4 Spiral Notebook 200 Pgs)")
    brand: str = Field(description="Brand name (e.g., Classmate, Cello, Doms, Apsara, Nataraj, Camlin, Flair, Hauser). If unknown, use 'Unknown'.")
    category: str = Field(description="Category (e.g., Pen, Notebook, Pencil, File/Folder, Adhesive, Stapler, Art/Craft, Office Supply)")
    quantity_in_pack: str = Field(description="Packaging unit (e.g., 'Single Piece', 'Pack of 5', 'Box of 10')")
    price_estimate: str = Field(description="Printed MRP (e.g., '₹10', '₹50') or estimated retail price")
    short_description: str = Field(description="Key specifications (e.g., '0.7mm blue ink', '200 ruled pages, spiral')")

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("💡 Balaji Growth Tip")
    st.info("The 3-Second Upsell: When a student buys stationery, always ask: **'PAN card bana liya? College ke baad kaam aayega, main yahan banata hoon.'**")

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
        st.warning("Please enter your Gemini API Key above or add it to Streamlit Secrets.")

client = None
if api_key:
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"Error initializing AI client: {e}")

# ─── Photo Input ─────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["📸 Take Photo", "📁 Upload Image"])

image_to_process = None

with tab1:
    camera_img = st.camera_input("Snap a photo of the stationery item")
    if camera_img:
        image_to_process = Image.open(camera_img)

with tab2:
    uploaded_file = st.file_uploader("Upload an item picture", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image_to_process = Image.open(uploaded_file)
        st.image(image_to_process, caption="Uploaded Image", width=350)

# ─── Analysis & Logging ──────────────────────────────────────────────────────

if image_to_process:
    st.markdown("---")
    quantity_to_add = st.number_input("📦 How many units are you adding to stock?", min_value=1, value=1, step=1)

    if st.button("✨ Analyze & Add to Google Sheets", type="primary", disabled=(client is None)):
        with st.spinner("Analyzing stationery item..."):
            prompt = "Extract the inventory details of this stationery item (brand, product name, category, pack count, printed price/MRP, and key specs)."
            
            success = False
            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=[image_to_process, prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=InventoryItem,
                            temperature=0.2,
                        ),
                    )

                    result_json = json.loads(response.text)

                    # Post directly to Google Form
                    form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfEKrFyFCMDc28A9fNlzoaQwT55ar7h6EsP4TMj5497BMWK-g/formResponse"
                    form_data = {
                        "entry.1048584284": result_json.get("item_name", ""),
                        "entry.1539118968": result_json.get("brand", ""),
                        "entry.1164511249": result_json.get("category", ""),
                        "entry.60721169": quantity_to_add,
                        "entry.1355037108": result_json.get("quantity_in_pack", ""),
                        "entry.1367724986": result_json.get("price_estimate", ""),
                        "entry.1644742150": result_json.get("short_description", "")
                    }

                    res = requests.post(form_url, data=form_data)
                    if res.status_code == 200:
                        st.success(f"☁️ Added **{quantity_to_add}x '{result_json.get('item_name', '')}'** ({result_json.get('price_estimate', '')}) to Google Sheets!")
                        st.json(result_json)
                        st.balloons()
                    else:
                        st.error(f"Failed to save to Google Sheets (Status code: {res.status_code})")

                    success = True
                    break

                except Exception as e:
                    if "503" in str(e) and attempt < 2:
                        st.warning(f"Server busy. Retrying in 3 seconds... (Attempt {attempt + 1}/3)")
                        time.sleep(3)
                    else:
                        st.error(f"Analysis failed: {e}")
                        break

            if not success:
                st.error("Could not complete analysis. Please try again in a moment.")