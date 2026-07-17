import os
import json
import requests
from langchain.tools import tool
import sys

# Add root directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.llm_client import llm
from utils.text_helper import truncate_or_save

# Load variables directly from environment (which was loaded by main/agent)
API_URL = os.getenv("WEB_BUILDER_API_URL", "http://localhost:8000")
API_TOKEN = os.getenv("WEB_BUILDER_API_TOKEN", "")

@tool
def search_web_builder_projects(project_name: str) -> str:
    """
    Search for AI Web Builder projects by name.
    Use this to find the project ID before generating a schema for it.
    Returns a JSON string of projects found (id, name, description).
    """
    if not API_TOKEN:
        return "Error: WEB_BUILDER_API_TOKEN is not configured in .env"
        
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Accept": "application/json"
    }
    try:
        url = f"{API_URL}/api/ai/projects/search?q={project_name}"
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        projects = response.json()
        if not projects:
            return f"No projects found matching '{project_name}'."
        return json.dumps(projects, indent=2)
    except Exception as e:
        return f"Error searching projects: {str(e)}"

@tool
def generate_and_save_web_builder_schema(project_id: int, prd_content: str) -> str:
    """
    Generate a JSON Schema based on user requirements and save it to the AI Web Builder Laravel backend.
    ALWAYS search for the project ID first using search_web_builder_projects before calling this!
    prd_content should be a detailed description of what the app should do, its features, and logic.
    """
    if not API_TOKEN:
        return "Error: WEB_BUILDER_API_TOKEN is not configured in .env"

    system_prompt = """You are an Expert Software Architect. Your task is to translate the provided Product Requirements Document (PRD) into a comprehensive JSON Schema blueprint.

You MUST output ONLY a valid JSON object matching the exact structure below. Do not wrap it in markdown code blocks, output only the raw JSON. The JSON structure:
{
    "models": [ { "name": "ModelName", "table": "table_name", "columns": [{ "name": "id", "type": "bigInteger", "unsigned": true, "autoIncrement": true, "primary": true }, { "name": "foreign_id", "type": "bigInteger", "unsigned": true, "index": true }, { "name": "col_name", "type": "string", "nullable": true }], "relations": [{"type": "hasMany", "model": "OtherModel", "foreign_key": "foreign_id"}] } ],
    "controllers": [ { "name": "ControllerName", "model": "ModelName", "functions": [
        { "name": "index", "description": "...", "ai_inject_logic": "Step by step logic for simple CRUD only" },
        { "name": "complexProcess", "type": "custom", "actions": [
             { "step": "check_condition", "condition": "{record.status} == 'paid'", "on_true_code": 400, "on_true_message": "Already paid" },
             { "step": "delete_record" }
        ] }
    ] } ],
    "routes": [ { "path": "/api/...", "method": "get", "access": { "require_auth": true, "roles": ["admin"] }, "controller": {"name": "ControllerName", "function": "index"} } ]
}

Make sure to create complete models, controllers for all major features (CRUD, business logic), and fully map out the routes.
CRITICAL RULE 1: For simple CRUD you may use `ai_inject_logic`. But for COMPLEX business logic, you MUST use `type: custom` (or `type: delete`) and the `actions` array with standard steps. Do NOT use `ai_inject_logic` if `actions` is used."""

    print(f"Generating JSON Schema for Project ID: {project_id}...")
    
    # Try using 9router model for better reasoning if available, fallback to default
    json_result = llm.ask(prompt=prd_content, system_prompt=system_prompt)
    
    json_result = json_result.strip()
    if json_result.startswith("```json"):
        json_result = json_result[7:]
    if json_result.startswith("```"):
        json_result = json_result[3:]
    if json_result.endswith("```"):
        json_result = json_result[:-3]
    json_result = json_result.strip()

    try:
        schema_dict = json.loads(json_result)
    except json.JSONDecodeError as e:
        return f"Error: The LLM failed to produce a valid JSON. Details: {e}\nRaw Output Snippet: {json_result[:200]}"

    print(f"Schema generated successfully. Pushing to Laravel API for Project ID: {project_id}...")
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "schema": schema_dict
    }
    
    try:
        url = f"{API_URL}/api/projects/{project_id}/schema"
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return f"Success! Schema saved and mapped automatically to Project ID {project_id}.\nLaravel Response: {data.get('message', 'OK')}"
    except Exception as e:
        error_details = ""
        if hasattr(e, 'response') and e.response is not None:
            error_details = e.response.text
        return f"Error saving schema to Laravel: {str(e)}\nDetails: {error_details}"

@tool
def deploy_web_builder_sandbox(project_id: int) -> str:
    """
    Deploy the latest saved schema of a project to the Sandbox Runner.
    Use this if the user asks to deploy or run the project after the schema is saved.
    """
    if not API_TOKEN:
        return "Error: WEB_BUILDER_API_TOKEN is not configured in .env"
        
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Accept": "application/json"
    }
    
    try:
        url = f"{API_URL}/api/projects/{project_id}/deploy-sandbox"
        response = requests.post(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        sandbox_url = data.get("sandbox_url", "Unknown URL")
        return f"Project deployed successfully! Access it at: {sandbox_url}"
    except Exception as e:
        error_details = ""
        if hasattr(e, 'response') and e.response is not None:
            error_details = e.response.text
        return f"Error deploying to sandbox: {str(e)}\nDetails: {error_details}"

@tool
def create_web_builder_project(name: str, backend_framework: str = "laravel", frontend_framework: str = "vue3") -> str:
    """
    Create a new AI Web Builder project.
    Use this when the user asks to create a new project.
    Returns the new Project ID, which should be used in subsequent PRD and Schema generation steps.
    """
    if not API_TOKEN:
        return "Error: WEB_BUILDER_API_TOKEN is not configured in .env"
        
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "name": name,
        "backend_framework": backend_framework,
        "frontend_framework": frontend_framework
    }
    
    try:
        url = f"{API_URL}/api/projects"
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        project_id = data.get("id")
        return f"Project '{name}' created successfully with ID {project_id}."
    except Exception as e:
        error_details = ""
        if hasattr(e, 'response') and e.response is not None:
            error_details = e.response.text
        return f"Error creating project: {str(e)}\nDetails: {error_details}"

@tool
def generate_and_save_prd(project_id: int, user_idea: str) -> str:
    """
    Generate a detailed Product Requirements Document (PRD) from a short user idea and save it to the Laravel backend.
    ALWAYS ensure you have the project_id (using search_web_builder_projects or create_web_builder_project) before calling this.
    """
    if not API_TOKEN:
        return "Error: WEB_BUILDER_API_TOKEN is not configured in .env"
        
    system_prompt = "You are an Expert Product Manager. Based on the user's idea, write a detailed Product Requirements Document (PRD) including project overview, core features, database entities needed, and user flows. Output purely the PRD in markdown format without wrapping in markdown code blocks."
    
    print(f"Generating PRD for Project ID: {project_id}...")
    prd_content = llm.ask(prompt=user_idea, system_prompt=system_prompt)
    prd_content = prd_content.strip()
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "content": prd_content
    }
    
    try:
        url = f"{API_URL}/api/projects/{project_id}/prd"
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        return f"PRD generated and saved successfully for Project ID {project_id}."
    except Exception as e:
        error_details = ""
        if hasattr(e, 'response') and e.response is not None:
            error_details = e.response.text
        return f"Error saving PRD: {str(e)}\nDetails: {error_details}"
