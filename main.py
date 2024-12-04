from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Dict, Optional
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
from fastapi.responses import FileResponse, JSONResponse
import json
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
import requests


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

def get_languages_from_json(file_path):
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
            # Assuming the JSON structure is a list at the root level
            if isinstance(data, list):
                return data
            else:
                raise ValueError("Invalid JSON structure: Expected a list.")
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        return []
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON.")
        return []
    except ValueError as e:
        print(f"Error: {e}")
        return []

def reset_state():
    """Helper function to reset the global state."""
    global current_business_index, current_language_index, extracted_data
    current_language_index = 0
    extracted_data.clear()

data_file = Path("business_data.json")
data_saved = Path("saved_data.json")

# Initialize the JSON file if it doesn't exist
if not data_file.exists():
    data_file.write_text("[]")

if not data_saved.exists():
    data_saved.write_text('{}')

language_path = "selected_languages.json"
languages = get_languages_from_json(language_path)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

def get_webdriver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service()  # Update this path
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

@app.get("/wayback/")
async def wayback_proxy(url: str):
    try:
        wayback_url = f"https://web.archive.org/web/timemap/json?url={url}&matchType=prefix&collapse=urlkey&output=json&fl=original,mimetype,timestamp,endtimestamp,groupcount,uniqcount&filter=!statuscode:[45]..&limit=50000"
        response = requests.get(wayback_url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

async def extract_data(business_name: str, languages: list) -> list:
    driver = get_webdriver()
    data = []
    try:
        for language in languages:
            # Notify WebSocket of current language
            message = {"event": "processing", "business": business_name, "language": language}
            await manager.broadcast(message)

            # Navigate to Google Maps
            driver.get("https://www.google.com/maps")
            time.sleep(2)  # Replace with a more robust wait strategy if necessary

            # Search for the business
            search_box = driver.find_element(By.ID, "searchboxinput")
            print(f"search_box: {search_box}")
            search_box.clear()
            search_box.send_keys(business_name)
            search_box.submit()
            time.sleep(5)  # Adjust or replace with an explicit wait

            # Change language
            current_url = driver.current_url
            new_url = f"{current_url.split('?')[0]}?hl={language}"
            driver.get(new_url)
            time.sleep(3)  # Adjust or replace with an explicit wait

            # Extract business name
            try:
                # Get the page title
                full_title = driver.find_element(By.TAG_NAME, "title").get_attribute("textContent")
                
                # Remove " - Google Maps" from the title
                if " - Google Maps" in full_title:
                    business_title = full_title.replace(" - Google Maps", "").strip()
                else:
                    business_title = full_title.strip()
            except Exception:
                business_title = "Name not found"

            data.append({"Business Name": business_title, "Language": language})

            # Notify WebSocket of progress
            await manager.broadcast(
                {"event": "language_completed", "business": business_name, "language": language}
            )

    finally:
        driver.quit()
    
    # Notify WebSocket of business completion
    await manager.broadcast({"event": "business_completed", "business": business_name})
    return data


def write_csv(business_name: str, data: list) -> str:
    csv_filename = f"{business_name.replace(' ', '_')}_data.csv"
    with open(csv_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Business Name", "Language"])
        writer.writerows([(item["Business Name"], item["Language"]) for item in data])
    return csv_filename

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Start automation
@app.post("/start-automation")
async def start_automation():
    

    business_names = read_json(data_file)

    if not isinstance(business_names, list) or not isinstance(languages, list):
        return JSONResponse(content={"error": "Invalid file formats"}, status_code=400)

    for business in business_names:
        extracted_data = await extract_data(business, languages)
        csv_file = write_csv(business, extracted_data)

        # Notify WebSocket that download is ready
        message = {"event": "download", "business": business, "csv_file": csv_file}
        await manager.broadcast(message)

    return JSONResponse(content={"message": "Automation completed. All CSV files are ready."})

# Utility to read JSON files
def read_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)

# Download CSV
@app.get("/download/{csv_filename}")
def download_csv(csv_filename: str):
    file_path = Path(csv_filename)
    if not file_path.exists():
        return JSONResponse(content={"error": "CSV file not found"}, status_code=404)
    return FileResponse(file_path, media_type="text/csv", filename=file_path.name)



# Define the path for the JSON data file


# Define a data model for the request body
class BusinessData(BaseModel):
    business_name: str

@app.post("/save")
def save_data(data: BusinessData):
    # Load the existing data from the file
    with data_file.open("r") as file:
        existing_data = json.load(file)
    
    # Append only the business name
    existing_data.append(data.business_name)
    
    # Save the updated data back to the file
    with data_file.open("w") as file:
        json.dump(existing_data, file)
    
    return {"status": "saved"}

# Pydantic model
class BusinessData(BaseModel):
    business_name: str
    value: str 

@app.post("/save_permanent")
def save_data(data: BusinessData):
    # Load the existing data from the file
    if data_saved.exists():
        with data_saved.open("r") as file:
            existing_data = json.load(file)
    else:
        existing_data = {}  # Initialize as an empty dictionary if the file doesn't exist

    # Ensure existing_data is a dictionary
    if not isinstance(existing_data, dict):
        existing_data = {}

    # Create a unique key using the business name
    unique_key = data.business_name

    # Add the new key-value pair to the dictionary
    existing_data[unique_key] = data.value

    # Save the updated data back to the file
    with data_saved.open("w") as file:
        json.dump(existing_data, file, indent=4)
    
    return {"status": "saved"}

@app.get("/get_saved_data")
def get_values():
    # Load the existing data from the file
    if data_saved.exists():
        with data_saved.open("r") as file:
            existing_data = json.load(file)
    else:
        existing_data = {}

    # Ensure existing_data is a dictionary
    if not isinstance(existing_data, dict):
        return {"error": "Data format is incorrect"}

    # Return all the values from the dictionary
    values = list(existing_data.values())
    return {"values": values}

@app.get("/retrieve")
def retrieve_data():
    # Load and return the data from the file
    with data_file.open("r") as file:
        data = json.load(file)
    return data


@app.delete("/delete-all")
def delete_all_data():
    # Clear the data in the JSON file by writing an empty list
    with data_file.open("w") as file:
        json.dump([], file)
    
    return {"status": "all data deleted"}


class LanguageRequest(BaseModel):
    languages: list[str]

@app.post("/save-languages")
def save_languages(request: LanguageRequest):
    try:
        with open("selected_languages.json", "w") as file:
            json.dump(request.languages, file)
        return {"message": "Languages saved successfully"}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/delete-saved")
async def delete_data(key: str):
    try:
        # Read the existing data from the JSON file
        with open(data_saved, 'r') as file:
            data = json.load(file)

        if key in data:
            del data[key]
            with open(data_saved, 'w') as file:
                json.dump(data, file, indent=4)
            return {"message": "Data deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Key not found")

    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Data file not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to decode JSON")


if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)