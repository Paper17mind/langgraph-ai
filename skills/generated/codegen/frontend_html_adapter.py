"""
Frontend HTML Adapter — generates static HTML files with Tailwind CSS and Alpine.js.
Uses Jinja2 templates.
"""
import os
import re
import jinja2
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "frontend_html")

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
    autoescape=False
)

def _to_kebab(s: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '-', s).lower()

class FrontendHtmlAdapter:
    def __init__(self, schema: dict, output_dir: str):
        self.schema = schema
        self.output_dir = output_dir

    def generate_all(self) -> dict[str, str]:
        files = {}

        all_models = self.schema.get("models", [])
        controllers = self.schema.get("controllers", [])
        
        # Only generate UI for models that have a controller
        controller_models = {ctrl.get("model") for ctrl in controllers if ctrl.get("model")}
        models = [m for m in all_models if m["name"] in controller_models]
        
        # Generate index.html
        template_idx = env.get_template("index.html.jinja2")
        idx_html = template_idx.render(models=models, to_kebab=_to_kebab)
        files["frontend/index.html"] = idx_html.strip()
            
        # Generate model pages
        template_page = env.get_template("page.html.jinja2")
        for model in models:
            page_html = template_page.render(model=model, models=models, to_kebab=_to_kebab)
            files[f"frontend/{_to_kebab(model['name'])}.html"] = page_html.strip()
            
        return files
