from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Dict, Optional
import csv
import time
from fastapi.responses import FileResponse, JSONResponse
import json
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

language_path = Path("selected_languages.json")
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


@app.get("/wayback/")
async def wayback_proxy(url: str):
    try:
        wayback_url = f"https://web.archive.org/web/timemap/json?url={url}&matchType=prefix&collapse=urlkey&output=json&fl=original,mimetype,timestamp,endtimestamp,groupcount,uniqcount&filter=!statuscode:[45]..&limit=50000"
        response = requests.get(wayback_url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

# Utility to read JSON files
def read_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


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

@app.get("/retrieve_lang")
def retrieve_lang():
    with language_path.open("r") as file:
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