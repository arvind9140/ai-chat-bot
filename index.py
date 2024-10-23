import os
import re
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
from pymongo import MongoClient
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

def clean_response_text(text):
    clean_text = re.sub(r'\*+', '', text)
    clean_text = re.sub(r'\<.*?\>', '', clean_text)
    clean_text = clean_text.replace('\n', ' ')
    clean_text = clean_text.strip()
    return clean_text

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
MONGODB_URI = os.getenv('MONGODB_URI')

client = MongoClient(MONGODB_URI)
db = client['interior_Design']
project_collection = "project"
lead_collection = "Lead"
user_collection = "users"

class QueryRequest(BaseModel):
    question: str

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/query/")
async def query_rag_system(request: QueryRequest):
    try:
        project_name = None
        lead_name = None
        context = None

        # Check for project name in the request
        match = re.search(r'project (\w+)', request.question, re.IGNORECASE)
        if match:
            project_name = match.group(1)

        # Check for lead name in the request
        match = re.search(r'lead (\w+)', request.question, re.IGNORECASE)
        print(match)
        if match:
            lead_name = match.group(1)

        # Retrieve project details if project name is found
        if project_name:
            project_details = db[project_collection].find_one({"project_name": project_name})
            if project_details:
                project_id = project_details.get("project_id") 
                if project_id:
                    assignees = list(db[user_collection].find({'data.projectData.project_id':project_id}))
                    usernames = [assignee['username'] for assignee in assignees if 'username' in assignee]
                    for username in usernames:
                        print(username)
                    project_details['assignees'] = usernames
                else:
                    project_details['assignees']=[]    
                context = project_details
            else:
                raise HTTPException(status_code=404, detail="Project not found.")

        # Retrieve lead details if lead name is found
       
        if lead_name:
            lead_details = db[lead_collection].find_one({"name": lead_name})
            if lead_details:
                lead_id = lead_details.get("lead_id")  
                
                if lead_id:
                  
                    assignees = list(db[user_collection].find({'data.leadData.lead_id': lead_id}))
                    usernames = [assignee['username'] for assignee in assignees if 'username' in assignee]

                   
                    lead_details['assignees'] = usernames
                else:
                    lead_details['assignees'] = [] 

                context = lead_details
            else:
                raise HTTPException(status_code=404, detail="Lead not found.")


        # If neither project nor lead is found, return an error
        if context is None:
            raise HTTPException(status_code=400, detail="No valid project or lead name found in the question.")

        # Prepare the request to the Gemini API
        gemini_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent'
        headers = {
            'Content-Type': 'application/json',
        }
        data = {
            "contents": [{
                "parts": [{
                    "text": f"Summarize the following details in no more than 100 words and do not give ID: '{request.question}' and the info: {context}."
                }]
            }]
        }

        # Call the Gemini API
        response = requests.post(f"{gemini_url}?key={OPENAI_API_KEY}", headers=headers, json=data)
        response_data = response.json()

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response_data.get("error", "Failed to generate response."))

        if response_data.get("candidates"):
            generated_response = response_data["candidates"][0]["content"]["parts"][0]["text"]
            generated_response = clean_response_text(generated_response)
        else:
            generated_response = "No response generated."

        # Streaming response generator
        async def event_generator():
            for chunk in generated_response.split('. '):  # Split by sentence for chunks
                yield f"data: {chunk.strip()}\n\n"
                await asyncio.sleep(1)  # Optional: wait before sending the next chunk

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
