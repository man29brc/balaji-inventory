import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime
from PIL import Image
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import requests

# Constants
EXCEL_FILE = "inventory.xlsx"

st.set_page_config(page_title="Balaji CSC Inventory", layout="centered")

st.title("Balaji CSC Smart Inventory")
st.markdown("Take a picture of any stationery item to automatically add it to your Excel sheet. (No data entry needed!)")

# Schema for Structured Output
class InventoryItem(BaseModel):
    item_name: str = Field(description="The specific name of the item (e.g., A4 Spiral Notebook, Cello Gripper Pen)")
    brand: str = Field(description="The brand of the item, if visible (e.g., Classmate, Cello, Camlin). If not visible, put 'Unknown'.")
    category: str = Field(description="The category of the item (e.g., Pen, Notebook, File, Craft, Accessory, Govt Form)")
    quantity_in_pack: str = Field(description="If it's a pack, how many inside? (e.g., 'Pack of 10', 'Single', 'Set of 5')")
    price_estimate: str = Field(description="Estimated price or MRP if visible. If not visible, leave empty.")
    short_description: str = Field(description="A brief description of color, size, or type.")

# Sidebar for config and upselling hint
with st.sidebar:
    st.header("Balaji Growth Tip")
    st.info("The 3-Second Upsell: When a student buys stationery, always ask: **'PAN card bana liya? College ke baad kaam aayega, main yahan banata hoon.'**")
    
# Main logic
api_key = None
try:
    api_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    pass

if not api_key:
    st.subheader("Setup")
    api_key = st.text_input("Enter your Gemini API Key:", type="password", help="Get this from Google AI Studio (aistudio.google.com)")
    if not api_key:
        st.warning("Please enter a Gemini API Key above or add it to Streamlit Secrets.")

client = None
if api_key:
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"Error initializing AI client: {e}")

# Tab for Camera vs File Upload
tab1, tab2 = st.tabs(["Take Picture", "Upload Image"])

image_to_process = None

with tab1:
    camera_image = st.camera_input("Take a clear picture of the item")
    if camera_image:
        image_to_process = Image.open(camera_image)
        st.image(image_to_process, caption="Captured Image", use_container_width=False, width=400)

with tab2:
    uploaded_file = st.file_uploader("Upload an image of the stationery item", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image_to_process = Image.open(uploaded_file)
        st.image(image_to_process, caption="Uploaded Image", use_container_width=False, width=400)

# Processing the image
if image_to_process:
    st.markdown("---")
    quantity_to_add = st.number_input("How many of these are you adding to stock?", min_value=1, value=1, step=1)
    
    if st.button("Analyze and Add to Inventory", type="primary", disabled=(client is None)):
        with st.spinner("Analyzing image using AI (this may take a few seconds if servers are busy)..."):
            import time
            success = False
            
            for attempt in range(3):
                try:
                    # Call Gemini
                    response = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=[
                            image_to_process, 
                            "Extract the inventory details of this stationery item. If it is multiple items, focus on the most prominent one or summarize the pack."
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=InventoryItem,
                            temperature=0.2,
                        ),
                    )
                    
                    # Parse JSON
                    result_json = json.loads(response.text)
                    
                    st.success("Analysis Complete!")
                    st.json(result_json)
                    
                    # Prepare data for Google Form
                    form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfEKrFyFCMDc28A9fNlzoaQwT55ar7h6EsP4TMj5497BMWK-g/formResponse"
                    form_data = {
                        "entry.1153844324": result_json.get("item_name", ""),
                        "entry.2079022739": result_json.get("brand", ""),
                        "entry.2010766534": result_json.get("category", ""),
                        "entry.2004142314": quantity_to_add,
                        "entry.1961838723": result_json.get("quantity_in_pack", ""),
                        "entry.1704120799": result_json.get("price_estimate", ""),
                        "entry.1024348240": result_json.get("short_description", "")
                    }
                    
                    try:
                        res = requests.post(form_url, data=form_data)
                        if res.status_code == 200:
                            st.success(f"☁️ Successfully added {quantity_to_add}x '{result_json.get('item_name', '')}' to Google Sheets!")
                        else:
                            st.error("Failed to save to Google Sheets. Status Code: " + str(res.status_code))
                    except Exception as e:
                        st.error(f"Failed to connect to Google Form: {e}")
                        
                    success = True
                    break # Break out of the loop if successful
                    
                except Exception as e:
                    if "503" in str(e) and attempt < 2:
                        st.warning(f"Google servers are currently busy (Attempt {attempt + 1}/3). Retrying in 3 seconds...")
                        time.sleep(3)
                    else:
                        st.error(f"Failed: {e}")
                        break
                    
            if not success:
                st.error("All attempts failed because Google's AI is too busy right now. Please try again in a few minutes!")