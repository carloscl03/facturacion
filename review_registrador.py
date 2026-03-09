"""Script to load and print registrador_service for review."""
import os
path = os.path.join(os.path.dirname(__file__), 'services', 'registrador_service.py')
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()
with open('_content.txt', 'w', encoding='utf-8') as out:
    out.write(content)
print("Wrote", len(content), "chars to _content.txt")
