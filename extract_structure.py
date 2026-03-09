"""Extract structure from registrador_service for review."""
import ast
import os

path = os.path.join(os.path.dirname(__file__), 'services', 'registrador_service.py')
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    source = f.read()

# Write source to file for reading
with open('struct_out.md', 'w', encoding='utf-8') as out:
    out.write("# Registrador service source\n\n```python\n")
    out.write(source)
    out.write("\n```\n")

try:
    tree = ast.parse(source)
    with open('struct_out.md', 'a', encoding='utf-8') as out:
        out.write("\n# Structure\n\n")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                out.write(f"- Function: {node.name} (line {node.lineno})\n")
            elif isinstance(node, ast.AsyncFunctionDef):
                out.write(f"- Async function: {node.name} (line {node.lineno})\n")
            elif isinstance(node, ast.ClassDef):
                out.write(f"- Class: {node.name} (line {node.lineno})\n")
except Exception as e:
    with open('struct_out.md', 'a', encoding='utf-8') as out:
        out.write(f"\nParse error: {e}\n")

print("Done")
