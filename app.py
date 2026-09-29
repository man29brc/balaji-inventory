import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime
from PIL import Image
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

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
st.subheader("Setup")
api_key_input = st.text_input("Enter your Gemini API Key:", type="password", help="Get this from Google AI Studio (aistudio.google.com)")

if not api_key_input:
    st.warning("Please enter a Gemini API Key above to enable AI analysis.")

client = None
try:
    if api_key_input:
        client = genai.Client(api_key=api_key_input)
except Exception as e:
    st.error(f"Error initializing AI client: {e}")

# Tab for Camera vs File Upload
tab1, tab2, tab3 = st.tabs(["Take Picture", "Upload Image", "View Excel"])

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

with tab3:
    if os.path.exists(EXCEL_FILE):
        df = pd.read_excel(EXCEL_FILE)
        # Using HTML rendering to bypass PyArrow App Control blocks on Windows
        st.markdown(df.to_html(index=False), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Download button
        with open(EXCEL_FILE, "rb") as file:
            st.download_button(
                label="Download Excel File",
                data=file,
                file_name=EXCEL_FILE,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.info("No inventory data found yet. Start adding items!")

# Processing the image
if image_to_process:
    st.markdown("---")
    quantity_to_add = st.number_input("How many of these are you adding to stock?", min_value=1, value=1, step=1)
    
    if st.button("Analyze and Add to Inventory", type="primary", disabled=(client is None)):
        with st.spinner("Analyzing image using AI..."):
            models_to_try = ['gemini-3.8-flash', 'gemini-1.5-flash', 'gemini-3.8-pro']
            success = False
            
            for model_name in models_to_try:
                try:
                    # Call Gemini
                    response = client.models.generate_content(
                        model=model_name,
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
                    
                    st.success(f"Analysis Complete! (Used {model_name})")
                    st.json(result_json)
                    
                    # Prepare data for Excel
                    new_row = {
                        "Date Added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Item Name": result_json.get("item_name", ""),
                        "Brand": result_json.get("brand", ""),
                        "Category": result_json.get("category", ""),
                        "Quantity Added": quantity_to_add,
                        "Pack Size": result_json.get("quantity_in_pack", ""),
                        "Price/MRP": result_json.get("price_estimate", ""),
                        "Description": result_json.get("short_description", "")
                    }
                    
                    df_new = pd.DataFrame([new_row])
                    
                    if os.path.exists(EXCEL_FILE):
                        df_existing = pd.read_excel(EXCEL_FILE)
                        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                    else:
                        df_combined = df_new
                        
                    df_combined.to_excel(EXCEL_FILE, index=False)
                    st.success(f"Successfully added {quantity_to_add}x '{new_row['Item Name']}' to {EXCEL_FILE}!")
                    success = True
                    break # Break out of the loop if successful
                    
                except Exception as e:
                    st.warning(f"Failed with {model_name}: {e}. Trying next model...")
                    
            if not success:
                st.error("All AI models are currently busy. Please try again in a minute.")