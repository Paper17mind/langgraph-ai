import os
import json
import datetime
import requests
import warnings

# Suppress the deprecation warning for google.generativeai
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
import google.generativeai as genai
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        
        self.ninerouter_key = os.getenv("9ROUTER_API_KEY", "")
        self.ninerouter_url = os.getenv("9ROUTER_URL", "https://9router.com/api/v1/chat/completions")
        self.ninerouter_model = os.getenv("9ROUTER_MODEL", "google/gemini-pro")
        
        self.router_model = os.getenv("ROUTER_MODEL", "groq")
        self.chat_model = os.getenv("CHAT_MODEL", "gemini")

        self.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(self.log_dir, exist_ok=True)

        # Initialize Groq
        if self.groq_key:
            self.groq_client = Groq(api_key=self.groq_key)
        else:
            self.groq_client = None

        # Initialize Gemini
        if self.gemini_key:
            genai.configure(api_key=self.gemini_key)
            # Default model
            self.gemini_model = genai.GenerativeModel('gemini-3.1-pro-preview')
        else:
            self.gemini_model = None

    def _log_request(self, model: str, prompt: str, system_prompt: str, response: str, tokens: dict = None):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.log_dir, "requests.jsonl")
        log_data = {
            "timestamp": timestamp,
            "model": model,
            "system_prompt": system_prompt,
            "prompt": prompt,
            "response": response,
            "tokens": tokens or {}
        }
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[Log Error]: {e}")

    def ask(self, prompt: str, system_prompt: str = None, use_model: str = None) -> str:
        """
        Send a prompt to the LLM.
        use_model can be 'groq' or 'gemini'. If None, uses self.chat_model.
        """
        model = use_model if use_model else self.chat_model
        response_text = "Error: Selected model is not configured or invalid."
        tokens = {}
        
        if model == "groq" and self.groq_client:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            try:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=messages,
                    model="llama-3.3-70b-versatile", # Fast and lightweight model
                    temperature=0.0
                )
                response_text = chat_completion.choices[0].message.content.strip()
                if hasattr(chat_completion, 'usage') and chat_completion.usage:
                    tokens = {
                        "prompt": getattr(chat_completion.usage, "prompt_tokens", 0),
                        "completion": getattr(chat_completion.usage, "completion_tokens", 0),
                        "total": getattr(chat_completion.usage, "total_tokens", 0)
                    }
            except Exception as e:
                response_text = f"Error with Groq: {e}"
                
        elif model == "gemini" and self.gemini_model:
            # Gemini system instructions can be set during initialization, but for dynamic system prompts
            # we can prepend it to the user prompt for simplicity in this lightweight version.
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"System Instruction: {system_prompt}\n\nUser Request: {prompt}"
            
            try:
                response = self.gemini_model.generate_content(full_prompt)
                response_text = response.text.strip()
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    tokens = {
                        "prompt": getattr(response.usage_metadata, 'prompt_token_count', 0),
                        "completion": getattr(response.usage_metadata, 'candidates_token_count', 0),
                        "total": getattr(response.usage_metadata, 'total_token_count', 0)
                    }
            except Exception as e:
                response_text = f"Error with Gemini: {e}"
                
        elif model == "9router":
            headers = {
                "Content-Type": "application/json"
            }
            if self.ninerouter_key:
                headers["Authorization"] = f"Bearer {self.ninerouter_key}"
                
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.ninerouter_model,
                "messages": messages,
                "temperature": 0.0
            }
            
            try:
                resp = requests.post(self.ninerouter_url, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                
                resp.encoding = 'utf-8'
                raw_text = resp.text.strip()
                # Remove "data: [DONE]" if 9router accidentally appends it
                if raw_text.endswith("data: [DONE]"):
                    raw_text = raw_text[:-12].strip()
                    
                data = json.loads(raw_text)
                response_text = data['choices'][0]['message']['content'].strip()
                if 'usage' in data:
                    tokens = {
                        "prompt": data['usage'].get("prompt_tokens", 0),
                        "completion": data['usage'].get("completion_tokens", 0),
                        "total": data['usage'].get("total_tokens", 0)
                    }
            except requests.exceptions.HTTPError as e:
                response_text = f"Error with 9router: {e.response.status_code} - {e.response.text}"
            except Exception as e:
                response_text = f"Error with 9router: {e}"
                
        self._log_request(model, prompt, system_prompt, response_text, tokens)
        return response_text

# Singleton instance
llm = LLMClient()
