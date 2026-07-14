import os
import history_manager
from router import detect_skill

import skills.chat_skill as chat_skill
import skills.system_skill as system_skill
import skills.scheduler_skill as scheduler_skill
import skills.http_skill as http_skill
import skills.web_search_skill as web_search_skill
import skills.coder_skill as coder_skill

SKILL_MAP = {
    "chat_skill": chat_skill,
    "system_skill": system_skill,
    "scheduler_skill": scheduler_skill,
    "http_skill": http_skill,
    "web_search_skill": web_search_skill,
    "coder_skill": coder_skill
}

def run_cli_bot():
    print("=======================================")
    print("   AI Assistant CLI Mode Started       ")
    print("   Type 'exit' or 'quit' to close      ")
    print("=======================================\n")
    
    while True:
        try:
            text = input("\nAssistant > ")
            if text.strip().lower() in ['exit', 'quit']:
                break
                
            if not text.strip():
                continue
                
            # 1. Route
            skill_name = detect_skill(text)
            print(f"[Router: Selected {skill_name}]")
            
            # Save User Message
            session_id = "cli_default"
            history_manager.add_message(session_id, "user", text)
            
            # 2. Execute
            skill_module = SKILL_MAP.get(skill_name, chat_skill)
            response = skill_module.execute(text, session_id=session_id)
            
            # Save Assistant Response
            history_manager.add_message(session_id, "assistant", response)
            
            # 3. Output
            print("\n" + response + "\n")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            
    print("\nExiting CLI...")
