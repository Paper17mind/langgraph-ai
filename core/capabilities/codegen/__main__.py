import argparse
import json
import sys
import os
from .engine import generate_project, ADAPTERS
from .schema import validate_schema_dict

def main():
    parser = argparse.ArgumentParser(description="Codegen Capability CLI")
    parser.add_argument("--schema", required=True, help="Path to project schema JSON file")
    parser.add_argument("--framework", required=True, choices=list(ADAPTERS.keys()), help="Target framework")
    parser.add_argument("--out", default="./generated_project", help="Output directory")
    parser.add_argument("--frontend", action="store_true", help="Also generate static frontend HTML pages")
    parser.add_argument("--validate-only", action="store_true", help="Only validate schema without generating files")

    args = parser.parse_args()

    if not os.path.exists(args.schema):
        print(f"Error: Schema file '{args.schema}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.schema, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        validated = validate_schema_dict(data)
        print(f"✓ Schema validation passed: {validated.project_name} ({len(validated.models)} models)")
    except Exception as e:
        print(f"✗ Schema validation failed: {e}", file=sys.stderr)
        sys.exit(1)

    if args.validate_only:
        sys.exit(0)

    try:
        res = generate_project(
            schema_data=data,
            framework=args.framework,
            output_dir=args.out,
            generate_frontend=args.frontend,
        )
        print(f"✓ Generation complete ({res['total_files']} files written to {res['output_dir']}).")
        if res["total_ai_jobs"] > 0:
            print(f"ℹ {res['total_ai_jobs']} function(s) require AI injection.")
    except Exception as e:
        print(f"✗ Generation error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
