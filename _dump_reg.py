# Temp script to dump registrador_service
with open('services/registrador_service.py', 'r', encoding='utf-8', errors='replace') as f:
    for i, line in enumerate(f, 1):
        print(f"{i:3d}| {line.rstrip()}")
