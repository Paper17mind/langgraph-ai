from llm_client import llm

# Define available skills and their descriptions for the router
AVAILABLE_SKILLS = {
    "system_skill": "Execute system or terminal commands (e.g., ls, df, restart service, open app).",
    "scheduler_skill": "Schedule tasks to run at a specific time or interval (e.g., remind me tomorrow, run backup every hour).",
    "http_skill": "Fetch data or content from a specific URL or API via HTTP requests.",
    "web_search_skill": "Search the internet for information, news, or answers to current events.",
    "coder_skill": "Write code, create files, edit scripts, or save text to a file in the system.",
    "chat_skill": "General conversation, answering questions, writing text, and everything else that doesn't fit the other skills."
}

def detect_skill(user_message: str) -> str:
    """
    Uses the fast LLM (Groq) to classify the intent of the user message and route it to the correct skill.
    """
    skill_descriptions = "\n".join([f"- {name}: {desc}" for name, desc in AVAILABLE_SKILLS.items()])
    
    system_prompt = f"""You are a highly accurate intent classifier for an AI assistant. 
Your only job is to read the user's message and classify it into exactly ONE of the following skill names:

{skill_descriptions}

Rules:
1. ONLY reply with the exact name of the skill. 
2. Do not include any other text, markdown, or explanations.
3. If it doesn't clearly match system, scheduler, http, or web search, ALWAYS default to 'chat_skill'.
"""
    
    # We use router_model (which defaults to 'groq' for speed)
    response = llm.ask(
        prompt=user_message,
        system_prompt=system_prompt,
        use_model=llm.router_model
    )
    
    # Clean response
    skill_name = response.strip().lower()
    
    # Fallback validation
    if skill_name not in AVAILABLE_SKILLS:
        skill_name = "chat_skill"
        
    return skill_name
