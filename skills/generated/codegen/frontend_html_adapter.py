"""
Frontend HTML Adapter — generates static HTML files with Tailwind CSS and Alpine.js.
Uses Jinja2 templates with DRY layout/component separation.

Structure generated:
  frontend/
    _layout.html      - base layout template (loaded via fetch)
    _components.js    - shared Alpine.js utilities (toast, confirm, etc.)
    index.html        - dashboard/home
    {model-plural}.html  - per-model CRUD page
"""
import os
import re
import jinja2

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "frontend_html")

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
    autoescape=False
)


# ─────────────────────────────────────────────
# String helpers
# ─────────────────────────────────────────────

def _to_kebab(s: str) -> str:
    """PascalCase / camelCase → kebab-case.  e.g. BookBorrow → book-borrow"""
    s = re.sub(r'((?<=[a-z0-9])[A-Z]|(?<=[A-Z])[A-Z](?=[a-z]))', r'-\1', s)
    return s.lower().lstrip('-')


def _to_plural_english(name: str) -> str:
    """
    Convert a model name (Pascal-case, possibly Indonesian) to a plural English API path.
    Examples:
      Transaksi    → transactions
      TransaksiDetail → transaction-details
      Pelanggan    → customers   (common Indonesian→English mappings)
      Book         → books
      Category     → categories
    """
    # Common Indonesian → English mappings
    ID_EN = {
        "transaksi": "transaction",
        "pelanggan": "customer",
        "layanan": "service",
        "barang": "item",
        "mutasibarang": "stock-mutation",
        "pengeluaran": "expense",
        "siswa": "student",
        "guru": "teacher",
        "kelas": "class",
        "mata-pelajaran": "subject",
        "nilai": "grade",
        "pembayaran": "payment",
        "produk": "product",
        "kategori": "category",
        "pesanan": "order",
        "pengguna": "user",
    }

    kebab = _to_kebab(name).lower()

    # Try full key first, then word-by-word
    if kebab in ID_EN:
        kebab = ID_EN[kebab]
    else:
        parts = kebab.split('-')
        parts = [ID_EN.get(p, p) for p in parts]
        kebab = '-'.join(parts)

    # Pluralise the last word (English rules)
    words = kebab.split('-')
    last = words[-1]
    if last.endswith(('s', 'x', 'z', 'ch', 'sh')):
        last += 'es'
    elif last.endswith('y') and not last[-2] in 'aeiou':
        last = last[:-1] + 'ies'
    else:
        last += 's'
    words[-1] = last
    return '-'.join(words)


def _get_fk_columns(model: dict, all_models: list) -> list:
    """
    Return list of (col, related_api_path) for every column whose name ends
    with '_id' AND whose prefix matches a known model name.
    e.g.  book_id → books,  transaction_id → transactions
    """
    model_map = {m['name'].lower(): m for m in all_models}
    result = []
    for col in model.get('columns', []):
        name = col.get('name', '')
        if name.endswith('_id'):
            prefix = name[:-3]  # strip _id
            # Try exact match in model names (strip underscores)
            matched_model = None
            for mn, m in model_map.items():
                if mn.replace(' ', '').lower() == prefix.replace('_', '').lower():
                    matched_model = m
                    break
                # Also check plural api path
                api = _to_plural_english(mn)
                if api.replace('-', '').rstrip('s') == prefix.replace('_', ''):
                    matched_model = m
                    break
            if matched_model:
                result.append({
                    'col': col,
                    'api': _to_plural_english(matched_model['name']),
                    'model_name': matched_model['name'],
                })
    return result


class FrontendHtmlAdapter:
    def __init__(self, schema: dict, output_dir: str):
        self.schema = schema
        self.output_dir = output_dir

    def generate_all(self) -> dict[str, str]:
        files = {}

        all_models = self.schema.get("models", [])
        controllers = self.schema.get("controllers", [])
        project_name = self.schema.get("project", "App")

        # Only generate UI for models that have a controller
        controller_models = {ctrl.get("model") for ctrl in controllers if ctrl.get("model")}
        models = [m for m in all_models if m["name"] in controller_models]

        # Enrich each model with computed fields used by templates
        enriched = []
        for m in models:
            enriched.append({
                **m,
                "api_path": _to_plural_english(m["name"]),
                "kebab_name": _to_kebab(m["name"]),
                "fk_columns": _get_fk_columns(m, all_models),
            })

        ctx = dict(
            models=enriched,
            project_name=project_name,
            to_kebab=_to_kebab,
            to_plural=_to_plural_english,
        )

        # ── Shared components JS
        tpl = env.get_template("_components.js.jinja2")
        files["_components.js"] = tpl.render(**ctx).strip()

        # ── Index / dashboard
        tpl = env.get_template("index.html.jinja2")
        files["index.html"] = tpl.render(**ctx).strip()

        # ── Per-model CRUD page
        tpl = env.get_template("page.html.jinja2")
        for m in enriched:
            page_ctx = {**ctx, "model": m}
            files[f"{m['api_path']}.html"] = tpl.render(**page_ctx).strip()

        return files
