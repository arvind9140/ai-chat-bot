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
TOKEN = os.getenv('TOKEN')

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
        lead_id = None

        # Check organisation
        check_org = db[org_collection].find_one({"_id": ObjectId(org_id)})
        if not check_org:
            raise HTTPException(
                status_code=404, detail="Organisation not found")

        # Check user
        check_user = db[user_collection].find_one(
            {"_id": ObjectId(user_id), "organization": org_id})
        if not check_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check for project name, lead name, and user name in the request

        if any(phrase in request.question.lower() for phrase in ["entire projects", "all projects", "whole projects", "all project"]):
            project_id = '00000000000'
        else:
            match = re.search(r'project (\w+)',
                              request.question, re.IGNORECASE)
            project_name = match.group(1) if match else None

        if any(phrase in request.question.lower() for phrase in ["entire leads", "all leads",  "all lead", "whole leads"]):
            lead_id = '111111'
        else:
            match = re.search(r'lead (\w+)', request.question, re.IGNORECASE)
            lead_name = match.group(1) if match else None

        match = re.search(r'user (\w+)', request.question, re.IGNORECASE)
        user_name = match.group(1) if match else None

        # Check user role
        role = check_user.get('role')
        if role in ['ADMIN', 'SUPERADMIN']:
            # Handle projects
            if project_id == '00000000000':
                projects = list(
                    db[project_collection].find({"org_id": org_id}))
                project_list = [
                    {
                        'project_name': project.get('project_name'),
                        'client_info': project.get('client'),
                        'phase': project.get('project_status'),
                    }
                    for project in projects
                ]
                context['projects'] = project_list
            else:
                if project_name:
                    project_details = db[project_collection].find_one(
                        {"project_name": project_name, "org_id": org_id})
                    if project_details:
                        project_id = project_details.get("project_id")
                        project_info = {k: v for k, v in project_details.items(
                        ) if k not in ['_id', 'project_id', 'org_id', 'fileId']}
                        project_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                            {'data.projectData.project_id': project_details.get('project_id'), "organization": org_id})]
                        context.update(project_info)
                    else:
                        context = {"message": "project not found"}

            # Handle leads
            if lead_id == '111111':
                leads = list(db[lead_collection].find({"org_id": org_id}))
                lead_list = [
                    {k: v for k, v in lead.items() if k not in [
                        '_id', 'lead_id', 'org_id', 'fileId']}
                    for lead in leads
                ]
                context['leads'] = lead_list
            else:
                if lead_name:
                    lead_details = db[lead_collection].find_one(
                        {"name": lead_name, "org_id": org_id})
                    if lead_details:
                        lead_id = lead_details.get("lead_id")
                        lead_info = {k: v for k, v in lead_details.items() if k not in [
                            '_id', 'lead_id', 'org_id']}
                        lead_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                            {'data.leadData.lead_id': lead_details.get('lead_id'), "organization": org_id})]
                        context.update(lead_info)
                    else:
                        context = {"message": "lead not found."}

            # Retrieve user details if user_name is provided
            if user_name:
                user_details = db[user_collection].find_one(
                    {"username": user_name, "organization": org_id})
                if user_details:
                    user_info = {k: v for k, v in user_details.items() if k not in [
                        '_id', 'org_id', 'organization', 'password', 'data', 'refreshToken', 'userProfile']}
                    org_details = db[org_collection].find_one(
                        {"_id": ObjectId(org_id)})
                    if org_details:
                        user_info['organisation_name'] = org_details.get(
                            'organization')
                    context.update(user_info)
                else:
                    raise HTTPException(
                        status_code=404, detail="User not found.")

        elif role in ['Senior Architect']:
            # Similar logic as above for Senior Architect
            if project_id == '00000000000':
                projects = list(
                    db[project_collection].find({"org_id": org_id}))
                project_list = [
                    {
                        'project_name': project.get('project_name'),
                        'client_info': project.get('client'),
                        'phase': project.get('project_status'),
                    }
                    for project in projects
                ]
                context['projects'] = project_list
            else:
                if project_name:
                    project_details = db[project_collection].find_one(
                        {"project_name": project_name, "org_id": org_id})
                    if project_details:
                        project_id = project_details.get("project_id")
                        project_info = {k: v for k, v in project_details.items(
                        ) if k not in ['_id', 'project_id', 'org_id', 'fileId']}
                        project_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                            {'data.projectData.project_id': project_details.get('project_id'), "organization": org_id})]
                        context.update(project_info)
                    else:
                        context = {"message": "Project not found."}

            # Handle leads
            if lead_id == '111111':
                leads = list(db[lead_collection].find({"org_id": org_id}))
                lead_list = [
                    {k: v for k, v in lead.items() if k not in [
                        '_id', 'lead_id', 'org_id', 'fileId']}
                    for lead in leads
                ]
                context['leads'] = lead_list
            else:
                if lead_name:
                    lead_details = db[lead_collection].find_one(
                        {"name": lead_name, "org_id": org_id})
                    if lead_details:
                        lead_id = lead_details.get("lead_id")
                        lead_info = {k: v for k, v in lead_details.items() if k not in [
                            '_id', 'lead_id', 'org_id']}
                        lead_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                            {'data.leadData.lead_id': lead_details.get('lead_id'), "organization": org_id})]
                        context.update(lead_info)
                    else:
                        context = {"message": "lead not found."}
        else:
            # For other roles, check access
            find_project = db[project_collection].find_one(
                {"project_name": project_name, "org_id": org_id})
            find_lead = db[lead_collection].find_one(
                {"name": lead_name, "org_id": org_id})

            if find_project:
                project_id = find_project.get("project_id")
                check_user_access = db[user_collection].find_one({"_id": ObjectId(
                    user_id), "organization": org_id, "data.projectData.project_id": project_id})
                if check_user_access:
                    project_info = {k: v for k, v in find_project.items() if k not in [
                        '_id', 'project_id', 'org_id']}
                    project_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                        {'data.projectData.project_id': project_id, "organization": org_id})]
                    context = project_info
                else:
                    context = {
                        "message": "You do not have access to get this project details."}
            elif find_lead:
                lead_id = find_lead.get("lead_id")
                check_user_access = db[user_collection].find_one({"_id": ObjectId(
                    user_id), "organization": org_id, "data.leadData.lead_id": lead_id})
                if check_user_access:
                    lead_info = {k: v for k, v in find_lead.items() if k not in [
                        '_id', 'lead_id', 'org_id']}
                    lead_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                        {'data.leadData.lead_id': lead_id, "organization": org_id})]
                    context = lead_info
                else:
                    context = {
                        "message": "You do not have access to this lead."}
            else:
                context = {"message": "You do not have access to get details."}

        # Prepare the request to the Gemini API
        # gemini_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent'
        initializ_url = 'https://colonelz.prod.devai.initz.run/initializ/v1/ai/chat'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {TOKEN}'
        }
        data = {

            "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that answers questions based on the provided context.",
                },
                {
                    "role": "user",
                    "content": f"Summarize the following details '{request.question}' and the info: {context}.",
                }
            ],
            "max_tokens": 5000,
            "temperature": 0.7,
            # "stream": False,
            "stream": True

        }

        # Call the Gemini API
        response = requests.post(
            initializ_url, headers=headers, json=data)
        if response.status_code == 200:
            print("Response Status: 200 OK")
        else:
            print(f"Error: {response.status_code}")
            # Print the raw content of the error response
            print("Error Response Content:")
            print(response.text)

        # Streaming response generator
        async def event_generator(project_id, lead_id):
            projectId = True
            leadId = True
            for chunk in response.iter_lines(decode_unicode=True):
                if chunk:
                    yield f"{chunk.strip()}\n\n"
                    # await asyncio.sleep(1)
                    if project_id:
                        if projectId:
                            yield f"data: project_id:{project_id}\n\n"
                            projectId = False
                    if lead_id:
                        if leadId:
                            yield f"data: lead_id:{lead_id}\n\n"
                            leadId = False

        return StreamingResponse(event_generator(project_id, lead_id), media_type="json/event-stream")

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
