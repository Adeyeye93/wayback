from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Optional
import csv
from fastapi.responses import FileResponse
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

@app.get("/wayback/")
async def wayback_proxy(url: str):
    try:
        wayback_url = f"https://web.archive.org/web/timemap/json?url={url}&matchType=prefix&collapse=urlkey&output=json&fl=original,mimetype,timestamp,endtimestamp,groupcount,uniqcount&filter=!statuscode:[45]..&limit=50000"
        response = requests.get(wayback_url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}



languages = [
    "af", "az","ur"
]

def reset_state():
    """Helper function to reset the global state."""
    global current_business_index, current_language_index, extracted_data
    current_language_index = 0
    extracted_data.clear()

# Define the path for the JSON data file
data_file = Path("business_data.json")
data_saved = Path("saved_data.json")

# Initialize the JSON file if it doesn't exist
if not data_file.exists():
    data_file.write_text("[]")

if not data_saved.exists():
    data_saved.write_text('{}')


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

# Example: Retrieve business names from the data file

# State tracking
current_business_index = 0
current_language_index = 0
extracted_data = []  # This will store tuples of (business name, language)

class DataRequest(BaseModel):
    business_name: str

@app.get("/next")
def get_next():
    businesses = retrieve_data()
    global current_business_index, current_language_index

    if current_business_index >= len(businesses):
        reset_state()
        return {"status": "done"} 

    # Get the current business name and language code
    business_name = businesses[current_business_index]
    language_code = languages[current_language_index]

    return {"business_name": business_name, "language": language_code}

@app.post("/submit")
def submit_data(data: DataRequest):
    businesses = retrieve_data()
    global current_language_index, current_business_index

    # Store the extracted business name and language
    language_code = languages[current_language_index]
    extracted_data.append((data.business_name, language_code))

    # Move to the next language
    current_language_index += 1
    if current_language_index >= len(languages):
        current_language_index = 0
        current_business_index += 1

        # Check if there are more businesses to process
        if current_business_index < len(businesses):
            return {"status": "next_business"}  # Signal to move to the next business
        else:
            return {"status": "done"}  # Signal that all businesses are processed

    return {"status": "success"}  # Continue processing the current business


@app.get("/download")
def download_csv():
    # Generate a CSV file with Business Name and Language columns
    csv_filename = "temporary_business_data.csv"
    with open(csv_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        # Write header
        writer.writerow(["Business Name", "Language"])
        # Write each business name and language pair
        writer.writerows(extracted_data)
        reset_state()
    return FileResponse(csv_filename, media_type="text/csv", filename=csv_filename)

@app.delete("/delete-all")
def delete_all_data():
    # Clear the data in the JSON file by writing an empty list
    with data_file.open("w") as file:
        json.dump([], file)
    
    return {"status": "all data deleted"}


if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)