# -*- coding: utf-8 -*-
"""Generate review of registrador_service.py"""
import os
path = os.path.join(os.path.dirname(__file__), 'services', 'registrador_service.py')
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

out_path = os.path.join(os.path.dirname(__file__), 'REVIEW_REGISTRADOR.md')
with open(out_path, 'w', encoding='utf-8') as out:
    out.write("# Revisión de registrador_service.py\n\n")
    out.write("## Código fuente\n\n```python\n")
    out.write(src)
    out.write("\n```\n")
print("Review written to", out_path)
