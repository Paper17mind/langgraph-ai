"""
Laravel adapter — generates PHP files for a Laravel 10+ API project.

Phase 1 (deterministic):
  - app/Models/{Model}.php          (Eloquent + fillable + relations)
  - database/migrations/            (Blueprint schema)
  - routes/api.php                  (Sanctum-guarded routes)
  - app/Http/Controllers/API/       (Controller stubs + standard action steps)
  - tests/Feature/                  (Pest tests for auth, roles, standard actions)

Phase 2 (LLM, via ai_inject_worker):
  - Replaces TODO placeholders in controllers with real logic
  - Appends companion test cases to existing test files
"""
import os
import re
from datetime import datetime
from .base_adapter import BaseAdapter


# -----------------------------------------------------------------------
# Column type mapping
# -----------------------------------------------------------------------
_TYPE_MAP = {
    "bigInteger": "bigInteger",
    "integer":    "integer",
    "string":     "string",
    "text":       "text",
    "boolean":    "boolean",
    "date":       "date",
    "datetime":   "dateTime",
    "decimal":    "decimal",
    "float":      "float",
    "json":       "json",
}

# -----------------------------------------------------------------------
# Relation helpers
# -----------------------------------------------------------------------
_RELATION_METHODS = {
    "hasMany":    "hasMany",
    "hasOne":     "hasOne",
    "belongsTo":  "belongsTo",
    "belongsToMany": "belongsToMany",
}


def _php_type(col: dict) -> str:
    return _TYPE_MAP.get(col.get("type", "string"), "string")


def _indent(text: str, spaces: int = 4) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())


class LaravelAdapter(BaseAdapter):

    # ==================================================================
    # Phase 1 — Models
    # ==================================================================

    def generate_models(self) -> dict[str, str]:
        files = {}
        for model_def in self.schema["models"]:
            name = model_def["name"]
            table = model_def["table"]
            columns = model_def.get("columns", [])
            relations = model_def.get("relations", [])

            # fillable = non-PK columns
            fillable_cols = [
                c["name"] for c in columns
                if not c.get("primary") and not c.get("autoIncrement")
            ]
            fillable_str = ", ".join(f"'{c}'" for c in fillable_cols)

            # cast map
            casts = {}
            for c in columns:
                if c.get("type") in ("date", "datetime"):
                    casts[c["name"]] = "date" if c["type"] == "date" else "datetime"
            cast_lines = "\n".join(f"        '{k}' => '{v}'," for k, v in casts.items())
            cast_block = (
                f"\n    protected $casts = [\n{cast_lines}\n    ];\n" if casts else ""
            )

            # relation methods
            relation_methods = []
            for rel in relations:
                rtype = rel["type"]
                related = rel["model"]
                fk = rel.get("foreign_key", "")
                method_name = _to_camel(related)
                if rtype in ("hasMany", "hasOne"):
                    method_name = _to_camel_plural(related) if rtype == "hasMany" else method_name
                method = (
                    f"    public function {method_name}(): "
                    f"\\Illuminate\\Database\\Eloquent\\Relations\\{_pascal(rtype)}\n"
                    f"    {{\n"
                    f"        return $this->{rtype}({related}::class, '{fk}');\n"
                    f"    }}"
                )
                relation_methods.append(method)

            relations_str = "\n\n".join(relation_methods)
            use_lines = "\n".join(
                f"use App\\Models\\{rel['model']};" for rel in relations
            )

            php = f"""<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;
use Illuminate\\Database\\Eloquent\\Factories\\HasFactory;
{use_lines}

class {name} extends Model
{{
    use HasFactory;

    protected $table = '{table}';

    protected $fillable = [{fillable_str}];
{cast_block}
{relations_str}
}}
"""
            files[f"app/Models/{name}.php"] = php.strip()
        return files

    # ==================================================================
    # Phase 1 — Migrations
    # ==================================================================

    def generate_migrations(self) -> dict[str, str]:
        files = {}
        base_ts = datetime.now()
        for i, model_def in enumerate(self.schema["models"]):
            ts = base_ts.strftime(f"%Y_%m_%d_%H%M{i:02d}")
            table = model_def["table"]
            columns = model_def.get("columns", [])

            col_lines = []
            for col in columns:
                if col.get("primary") or col.get("autoIncrement"):
                    col_lines.append("            $table->id();")
                    continue
                t = _php_type(col)
                args = f"'{col['name']}'"
                if t == "string" and col.get("length"):
                    args += f", {col['length']}"
                line = f"            $table->{t}({args})"
                if col.get("nullable"):
                    line += "->nullable()"
                if col.get("unique"):
                    line += "->unique()"
                if col.get("index"):
                    line += "->index()"
                if "default" in col:
                    dv = col["default"]
                    dv_str = f"'{dv}'" if isinstance(dv, str) else str(dv)
                    line += f"->default({dv_str})"
                if col.get("unsigned"):
                    line += "->unsigned()"
                line += ";"
                col_lines.append(line)

            col_lines.append("            $table->timestamps();")
            cols_str = "\n".join(col_lines)

            php = f"""<?php

use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

return new class extends Migration
{{
    public function up(): void
    {{
        Schema::create('{table}', function (Blueprint $table) {{
{cols_str}
        }});
    }}

    public function down(): void
    {{
        Schema::dropIfExists('{table}');
    }}
}};
"""
            files[f"database/migrations/{ts}_create_{table}_table.php"] = php.strip()
        return files

    # ==================================================================
    # Phase 1 — Routes
    # ==================================================================

    def generate_routes(self) -> dict[str, str]:
        # Group routes by roles/auth
        ctrl_imports = set()
        route_lines = []

        for route in self.routes:
            path = route["path"].replace("{id}", "{id}")
            method = route["method"]
            ctrl_info = route["controller"]
            ctrl_name = ctrl_info["name"]
            fn_name = ctrl_info["function"]
            access = route.get("access", {})
            roles = access.get("roles", [])

            ctrl_imports.add(ctrl_name)
            role_middleware = ""
            if roles and roles != ["admin", "student"]:
                roles_str = "|".join(roles)
                role_middleware = f"->middleware('role:{roles_str}')"

            line = (
                f"    Route::{method}('{path}', [{ctrl_name}::class, '{fn_name}'])"
                f"{role_middleware};"
            )
            route_lines.append(line)

        imports = "\n".join(
            f"use App\\Http\\Controllers\\API\\{c};" for c in sorted(ctrl_imports)
        )
        routes_str = "\n".join(route_lines)

        php = f"""<?php

use Illuminate\\Support\\Facades\\Route;
{imports}

Route::middleware('auth:sanctum')->group(function () {{
{routes_str}
}});
"""
        return {"routes/api.php": php.strip()}

    # ==================================================================
    # Phase 1 — Controllers
    # ==================================================================

    def generate_controllers(self) -> dict[str, str]:
        files = {}
        for ctrl in self.controllers:
            ctrl_name = ctrl["name"]
            model_name = ctrl.get("model", "")
            functions_code = []

            for fn in ctrl.get("functions", []):
                fn_name = fn["name"]
                fn_type = fn.get("type", "standard")
                ai_logic = fn.get("ai_inject_logic")

                if ai_logic:
                    # Placeholder for Phase 2
                    body = (
                        f"        // TODO: ai_inject_logic — {ai_logic}\n"
                        f"        // This function will be generated by the AI background worker.\n"
                        f"        return response()->json(['message' => 'Not yet implemented'], 501);"
                    )
                elif fn_type == "custom" or "actions" in fn:
                    body = self._generate_action_steps(fn.get("actions", []), model_name)
                else:
                    body = self._generate_standard_fn(fn_name, model_name)

                param = self._fn_param(fn_name, model_name)
                fn_code = f"    public function {fn_name}({param})\n    {{\n{body}\n    }}"
                functions_code.append(fn_code)

            use_lines = f"use App\\Models\\{model_name};\nuse Illuminate\\Http\\Request;"
            fns_str = "\n\n".join(functions_code)

            php = f"""<?php

namespace App\\Http\\Controllers\\API;

use App\\Http\\Controllers\\Controller;
{use_lines}

class {ctrl_name} extends Controller
{{
{fns_str}
}}
"""
            files[f"app/Http/Controllers/API/{ctrl_name}.php"] = php.strip()
        return files

    def _fn_param(self, fn_name: str, model: str) -> str:
        if fn_name in ("show", "update", "destroy"):
            return f"Request $request, {model} ${model[0].lower() + model[1:]}"
        return "Request $request"

    def _generate_standard_fn(self, fn_name: str, model: str) -> str:
        var = "$" + model[0].lower() + model[1:]
        m = model
        if fn_name == "index":
            return f"        return response()->json({m}::all());"
        if fn_name == "store":
            return (
                f"        $data = $request->validated();\n"
                f"        {var} = {m}::create($data);\n"
                f"        return response()->json({var}, 201);"
            )
        if fn_name == "show":
            return f"        return response()->json({var});"
        if fn_name == "update":
            return (
                f"        {var}->update($request->validated());\n"
                f"        return response()->json({var});"
            )
        if fn_name == "destroy":
            return (
                f"        {var}->delete();\n"
                f"        return response()->json(null, 204);"
            )
        return f"        // TODO: implement {fn_name}"

    def _generate_action_steps(self, actions: list, model: str) -> str:
        lines = []
        var = "$" + model[0].lower() + model[1:]

        for action in actions:
            step = action.get("step", "")

            if step == "check_condition":
                cond = action["condition"]
                code = action["on_true_code"]
                msg = action["on_true_message"]
                php_cond = _translate_condition(cond, var)
                lines.append(
                    f"        if ({php_cond}) {{\n"
                    f"            return response()->json(['message' => '{msg}'], {code});\n"
                    f"        }}"
                )

            elif step == "check_relation_empty":
                rel_model = action["relation_model"]
                fk = action["foreign_key"]
                code = action["on_fail_code"]
                msg = action["on_fail_message"]
                rel_method = _to_camel_plural(rel_model)
                lines.append(
                    f"        if ({var}->{rel_method}()->exists()) {{\n"
                    f"            return response()->json(['message' => '{msg}'], {code});\n"
                    f"        }}"
                )

            elif step == "set_field":
                field = action["field"]
                value = action["value"]
                php_val = "now()" if value == "now" else f"'{value}'"
                lines.append(
                    f"        {var}->{field} = {php_val};\n"
                    f"        {var}->save();"
                )

            elif step == "update_related_record":
                rel_model = action["relation_model"]
                fk = action["foreign_key"]
                field = action["field"]
                act = action["action"]  # increment | decrement
                rel_var = "$" + rel_model[0].lower() + rel_model[1:]
                lines.append(
                    f"        {rel_var} = {rel_model}::find({var}->{fk});\n"
                    f"        if ({rel_var}) {rel_var}->{act}('{field}');"
                )

            elif step == "calculate_and_insert":
                target = action["target_model"]
                fields = action.get("fields", {})
                trigger = action.get("condition_trigger", "true")
                field_lines = []
                for k, v in fields.items():
                    if "{" in v:
                        php_v = _resolve_template_var(v, var)
                    elif v == "now":
                        php_v = "now()"
                    else:
                        php_v = f"'{v}'"
                    field_lines.append(f"                '{k}' => {php_v},")
                fields_str = "\n".join(field_lines)
                cond_str = "" if trigger == "true" else f"if ({_translate_condition(trigger, var)}) "
                lines.append(
                    f"        {cond_str}{target}::create([\n{fields_str}\n        ]);"
                )

            elif step == "send_notification":
                notif = action["notification_name"]
                recipient = action.get("recipient", "user")
                lines.append(
                    f"        // Notification: {notif}\n"
                    f"        // \\Illuminate\\Support\\Facades\\Notification::send"
                    f"($request->user(), new \\App\\Notifications\\{notif}({var}));"
                )

            elif step == "dispatch_job":
                job = action["job_name"]
                payload = action.get("payload", {})
                payload_str = ", ".join(f"'{k}' => {_resolve_template_var(str(v), var)}" for k, v in payload.items())
                lines.append(f"        \\App\\Jobs\\{job}::dispatch([{payload_str}]);")

            elif step == "delete_record":
                lines.append(
                    f"        {var}->delete();\n"
                    f"        return response()->json(null, 204);"
                )

        if not any("return response()" in l for l in lines):
            lines.append(f"        return response()->json({var});")

        return "\n\n".join(lines)

    # ==================================================================
    # Phase 1 — Tests (Pest)
    # ==================================================================

    def generate_tests_phase1(self) -> dict[str, str]:
        files = {}
        for ctrl in self.controllers:
            ctrl_name = ctrl["name"]
            model_name = ctrl.get("model", "")
            test_cases = []

            # Auth guard tests
            for route in self.routes:
                ctrl_info = route["controller"]
                if ctrl_info["name"] != ctrl_name:
                    continue
                method = route["method"]
                path = route["path"].replace("{id}", "1")
                access = route.get("access", {})
                if access.get("require_auth"):
                    test_cases.append(
                        f"test('unauthenticated cannot {method} {route[\"path\"]}', function () {{\n"
                        f"    $response = $this->{method}Json('/api{path}');\n"
                        f"    $response->assertUnauthorized();\n"
                        f"}});"
                    )

            # Standard action assertions
            for fn in ctrl.get("functions", []):
                for action in fn.get("actions", []):
                    step = action.get("step")
                    if step == "check_condition":
                        msg = action["on_true_message"]
                        code = action["on_true_code"]
                        test_cases.append(
                            f"test('{ctrl_name}.{fn['name']}: returns {code} when condition met', function () {{\n"
                            f"    // Condition: {action['condition']}\n"
                            f"    // Expected: {code} '{msg}'\n"
                            f"    $this->markTestIncomplete('Fill in setup for this condition test.');\n"
                            f"}});"
                        )
                    elif step == "check_relation_empty":
                        msg = action["on_fail_message"]
                        code = action["on_fail_code"]
                        test_cases.append(
                            f"test('{ctrl_name}.{fn['name']}: returns {code} when relation exists', function () {{\n"
                            f"    // Expected: {code} '{msg}'\n"
                            f"    $this->markTestIncomplete('Fill in setup with related records.');\n"
                            f"}});"
                        )

            if test_cases:
                cases_str = "\n\n".join(test_cases)
                php = f"""<?php

use Illuminate\\Foundation\\Testing\\RefreshDatabase;

uses(RefreshDatabase::class);

// Auto-generated Phase 1 tests for {ctrl_name}
// Auth guards and standard action assertions.
// Phase 2 will append ai_inject_logic function tests.

{cases_str}
"""
                files[f"tests/Feature/{ctrl_name}Test.php"] = php.strip()
        return files

    # ==================================================================
    # Phase 2 — AI inject helpers
    # ==================================================================

    def build_ai_inject_prompt(
        self,
        controller_name: str,
        function_name: str,
        ai_inject_logic: str,
        model_name: str,
    ) -> str:
        model = self.models.get(model_name, {})
        cols = model.get("columns", [])
        rels = model.get("relations", [])

        col_desc = ", ".join(
            f"{c['name']} ({c.get('type','string')})" for c in cols
        )
        rel_desc = "; ".join(
            f"{r['type']} {r['model']} via {r.get('foreign_key','')}"
            for r in rels
        )

        # Include related model columns for context
        related_ctx = []
        for rel in rels:
            rm = self.models.get(rel["model"], {})
            if rm:
                rc = ", ".join(c["name"] for c in rm.get("columns", []))
                related_ctx.append(f"  - {rel['model']}: {rc}")
        related_str = "\n".join(related_ctx) if related_ctx else "  (none)"

        return (
            f"You are a Laravel 10 expert. Generate ONLY the PHP function body "
            f"(the code inside the curly braces) for the following method.\n\n"
            f"Controller: {controller_name}\n"
            f"Function: {function_name}\n"
            f"Task: {ai_inject_logic}\n\n"
            f"Primary Model: {model_name}\n"
            f"  Columns: {col_desc}\n"
            f"  Relations: {rel_desc}\n\n"
            f"Related Models:\n{related_str}\n\n"
            f"Requirements:\n"
            f"- Use Eloquent ORM\n"
            f"- Return response()->json(...)\n"
            f"- Use $request->validated() for input\n"
            f"- Do NOT include the function signature, only the body\n"
            f"- No markdown, no explanation, pure PHP code only\n"
        )

    def inject_ai_code(
        self,
        file_path: str,
        function_name: str,
        generated_code: str,
    ) -> None:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        placeholder = f"        // TODO: ai_inject_logic"
        # Find the function block containing this placeholder
        pattern = (
            rf"(public function {re.escape(function_name)}\([^)]*\)\s*\{{\n)"
            rf"(.*?// TODO: ai_inject_logic.*?)\n(\s*\}})"
        )
        replacement = rf"\g<1>{_indent(generated_code.strip(), 8)}\n\g<3>"
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _pascal(s: str) -> str:
    return s[0].upper() + s[1:] if s else s

def _to_camel(s: str) -> str:
    return s[0].lower() + s[1:] if s else s

def _to_camel_plural(s: str) -> str:
    base = _to_camel(s)
    return base + "s" if not base.endswith("s") else base

def _translate_condition(cond: str, var: str) -> str:
    """Translate schema condition DSL to PHP expression."""
    cond = cond.strip()
    # e.g. "book->stock < 1"  → "$book->stock < 1"
    cond = re.sub(r'\b([a-z][a-zA-Z]*)->(\w+)', r'$\1->\2', cond)
    # e.g. "return_date != null" → "$model->return_date !== null"
    cond = re.sub(r'\b(\w+)\s*!=\s*null', rf'{var}->\1 !== null', cond)
    cond = re.sub(r'\b(\w+)\s*==\s*null', rf'{var}->\1 === null', cond)
    cond = re.sub(r"==\s*'([^']+)'", r"=== '\1'", cond)
    return cond

def _resolve_template_var(v: str, var: str) -> str:
    """Resolve {field} template to PHP variable access."""
    v = re.sub(r'\{(\w+)\}', rf'{var}->\\1', v)
    v = re.sub(r'\{auth_user_id\}', '$request->user()->id', v)
    return v
