import os
import re
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
from pymongo import MongoClient
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId
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
org_collection = "organisation"

class QueryRequest(BaseModel):
    question: str
    org_id: str
    user_id: str

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
        context = {}
        org_id = request.org_id
        user_id = request.user_id
        project_id = None
        
        # Check organisation
        check_org = db[org_collection].find_one({"_id": ObjectId(org_id)})
        if not check_org:   
            raise HTTPException(status_code=404, detail="Organisation not found")

        # Check user
        check_user = db[user_collection].find_one({"_id": ObjectId(user_id), "organization": org_id})
        if not check_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check for project name and lead name in the request
        match = re.search(r'project (\w+)', request.question, re.IGNORECASE)
        project_name = match.group(1) if match else None

        match = re.search(r'lead (\w+)', request.question, re.IGNORECASE)
        lead_name = match.group(1) if match else None

        match = re.search(r'user (\w+)', request.question, re.IGNORECASE)
        user_name = match.group(1) if match else None
        # Check user role
        role = check_user.get('role')
        if role in ['ADMIN', 'SUPERADMIN']:
            # Retrieve project details
            if project_name:
                project_details = db[project_collection].find_one({"project_name": project_name, "org_id": org_id})
                if project_details:
                    # Exclude ID from context
                    project_id = project_details.get("project_id")
                    project_info = {k: v for k, v in project_details.items() if k not in ['_id', 'project_id','org_id','fileId',]}
                    project_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find({'data.projectData.project_id': project_details.get('project_id'), "organization": org_id})]
                    context = project_info
                else:
                    raise HTTPException(status_code=404, detail="Project not found.")

            # Retrieve lead details
            if lead_name:
                lead_details = db[lead_collection].find_one({"name": lead_name, "org_id": org_id})
                if lead_details:
                    # Exclude ID from context
                    lead_info = {k: v for k, v in lead_details.items() if k not in ['_id', 'lead_id', 'org_id']}
                    lead_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find({'data.leadData.lead_id': lead_details.get('lead_id'), "organization": org_id})]
                    context = lead_info
                else:
                    raise HTTPException(status_code=404, detail="Lead not found.")

            # Retrieve user details
            if user_name:
                    user_details = db[user_collection].find_one({"username": user_name, "organization": org_id})
                    if user_details:
                        # Exclude ID from context
                        user_info = {k: v for k, v in user_details.items() if k not in ['_id', 'org_id','organization','password','data','refreshToken','userProfile']}
                        
                        # Fetch the organization name
                        org_details = db[org_collection].find_one({"_id": ObjectId(org_id)})
                        if org_details:
                            user_info['organisation_name'] = org_details.get('organization')  # Assuming the name field contains the organization name
                            
                        context = user_info
                    else:
                        raise HTTPException(status_code=404, detail="User not found.")

            projects = list(db[project_collection].find({"org_id": org_id}))
            project_list = [
                    {
                        'project_name': project.get('project_name'),
                        'client_info': project.get('client'),
                        'phase': project.get('project_status'),  
                        
                    }
                    for project in projects
                ]
            context['projects'] = project_list

            leads = list(db[lead_collection].find({"org_id": org_id}))
            
            lead_list = [
                {k: v for k, v in lead.items() if k not in ['_id', 'lead_id', 'org_id', 'fileId']}
                for lead in leads
            ]
            context['leads'] = lead_list
        elif role in ['Senior Architect']:
            # Similar logic as above for Senior Architect
            if project_name:
                project_details = db[project_collection].find_one({"project_name": project_name, "org_id": org_id})
                if project_details:
                    project_id = project_details.get("project_id")
                    project_info = {k: v for k, v in project_details.items() if k not in ['_id', 'project_id', 'org_id', 'fileId']}
                    project_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find({'data.projectData.project_id': project_details.get('project_id'), "organization": org_id})]
                    context = project_info
                else:
                    raise HTTPException(status_code=404, detail="Project not found.")

            # Retrieve lead details
            if lead_name:
                lead_details = db[lead_collection].find_one({"name": lead_name, "org_id": org_id})
                if lead_details:
                    lead_info = {k: v for k, v in lead_details.items() if k not in ['_id', 'lead_id','org_id']}
                    lead_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find({'data.leadData.lead_id': lead_details.get('lead_id'), "organization": org_id})]
                    context = lead_info
                else:
                    raise HTTPException(status_code=404, detail="Lead not found.")
 
            projects = list(db[project_collection].find({"org_id": org_id}))
            project_list = [
                    {
                        'project_name': project.get('project_name'),
                        'client_info': project.get('client'),
                        'phase': project.get('project_status'),
                        
                    }
                    for project in projects
                ]
            context['projects'] = project_list

            leads = list(db[lead_collection].find({"org_id": org_id}))
            
            lead_list = [
                {k: v for k, v in lead.items() if k not in ['_id', 'lead_id', 'org_id', 'fileId']}
                for lead in leads
            ]
            context['leads'] = lead_list
        else:
            # For other roles, check access
            find_project = db[project_collection].find_one({"project_name": project_name, "org_id": org_id})
            find_lead = db[lead_collection].find_one({"name": lead_name, "org_id": org_id})

            if find_project:
                project_id = find_project.get("project_id")
                check_user_access = db[user_collection].find_one({"_id": ObjectId(user_id), "organization": org_id, "data.projectData.project_id": project_id})
                if check_user_access:
                    project_info = {k: v for k, v in find_project.items() if k not in ['_id', 'project_id', 'org_id']}
                    project_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find({'data.projectData.project_id': project_id, "organization": org_id})]
                    context = project_info
                else:
                    context = {"message": "You do not have access to get this project details."}
            elif find_lead:
                lead_id = find_lead.get("lead_id")
                check_user_access = db[user_collection].find_one({"_id": ObjectId(user_id), "organization": org_id, "data.leadData.lead_id": lead_id})
                if check_user_access:
                    lead_info = {k: v for k, v in find_lead.items() if k not in ['_id', 'lead_id', 'org_id']}
                    lead_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find({'data.leadData.lead_id': lead_id, "organization": org_id})]
                    context = lead_info
                else:
                    context = {"message": "You do not have access to this lead."}
            else:
                context = {"message": "You do not have access to get details."}

        # Prepare the request to the Gemini API
        gemini_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent'
        headers = {
            'Content-Type': 'application/json',
        }
        data = {
            "contents": [{
                "parts": [{
                    "text": f"Summarize the following details in no more than 100 words: '{request.question}' and the info: {context}."
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
        async def event_generator(project_id):
            projectId = True
            for chunk in generated_response.split('. '):  
                yield f"data: {chunk.strip()}\n\n"
                await asyncio.sleep(1)
                if projectId:
                    yield f"data: project_id:{project_id}\n\n"
                    projectId = False  

        return StreamingResponse(event_generator(project_id), media_type="text/event-stream")

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
