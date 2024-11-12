from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Optional
import csv
from fastapi.responses import FileResponse
import json
from pathlib import Path
from fastapi.middleware.cors import CORSMiddlewaree
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET"],
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
    "af", "az", "id", "ms", "bs", "ca", "cs", "da", "de", "et",
    "en", "es", "es-419", "eu", "fil", "fr", "gl", "hr", "zu",
    "is", "it", "sw", "lv", "lt", "hu", "nl", "no", "uz", "pl",
    "pt-BR", "pt-PT", "ro", "sq", "sk", "sl", "fi", "sv", "vi",
    "tr", "el", "bg", "ky", "kk", "mk", "mn", "ru", "sr", "uk",
    "ka", "hy", "he", "ur", "ar", "fa", "am", "ne", "hi", "mr",
    "bn", "pa", "gu", "ta", "te", "kn", "ml", "si", "th", "lo",
    "my", "km", "ko", "ja", "zh-CN", "zh-TW"
]


data_file = Path("business_data.json")

# Initialize the JSON file if it doesn't exist
if not data_file.exists():
    data_file.write_text("[]")

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

@app.get("/retrieve")
def retrieve_data():
    # Load and return the data from the file
    with data_file.open("r") as file:
        data = json.load(file)
    return data
# Example: Retrieve business names from the data file
businesses = retrieve_data()

# State tracking
current_business_index = 0
current_language_index = 0
extracted_data = []  # This will store only business names

class DataRequest(BaseModel):
    business_name: str

@app.get("/next")
def get_next():
    global current_business_index, current_language_index

    if current_business_index >= len(businesses):
        return {"status": "done"} 

    business_name = businesses[current_business_index]
    language_code = languages[current_language_index]

    return {"business_name": business_name, "language": language_code}

@app.post("/submit")
def submit_data(data: DataRequest):
    global current_language_index, current_business_index

    # Store the extracted business name
    extracted_data.append(data.business_name)

    # Move to the next language
    current_language_index += 1
    if current_language_index >= len(languages):
        current_language_index = 0
        current_business_index += 1

    # Delete the processed business name if we finished all languages
    if current_language_index == 0 and current_business_index > 0:
        businesses.pop(current_business_index - 1)

    if current_business_index >= len(businesses):
        return {"status": "done"}

    return {"status": "success"}

@app.get("/download")
def download_csv():
    # Generate a CSV file
    csv_filename = "business_report.csv"
    with open(csv_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Business Name"])
        writer.writerows([[name] for name in extracted_data])

    return FileResponse(csv_filename, media_type="text/csv", filename=csv_filename)

if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)