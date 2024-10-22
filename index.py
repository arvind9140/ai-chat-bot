import os
import re
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
from pymongo import MongoClient
from pydantic import BaseModel
from langchain_openai import OpenAIEmbeddings
from langchain_openai import OpenAI
from langchain.prompts import PromptTemplate
from langchain_mongodb import MongoDBAtlasVectorSearch
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

# Configure embeddings
embeddings = OpenAIEmbeddings()
project_vector_store = MongoDBAtlasVectorSearch(collection=project_collection, embedding=embeddings)

llm = OpenAI(model_name="gemini-1.5-flash-latest")  

class QueryRequest(BaseModel):
    question: str

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins, adjust as necessary
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

@app.post("/query/")
async def query_rag_system(request: QueryRequest):
    try:
        match = re.search(r'project (\w+)', request.question, re.IGNORECASE)
        if match:
            project_name = match.group(1)
        else:
            raise HTTPException(status_code=400, detail="Project name not found in the question.")
        
        project_details = db[project_collection].find_one({"project_name": project_name})
        
        if not project_details:
            raise HTTPException(status_code=404, detail="Project not found.")
        
        context = project_details 
       
        # Prepare the request to Gemini API
        gemini_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent'
        headers = {
            'Content-Type': 'application/json',
        }
        data = {
            "contents": [{
                "parts": [{
                     "text": f"Summarize the following project details in no more than 100 words and not give id: '{request.question}' and the project info: {context}."
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
