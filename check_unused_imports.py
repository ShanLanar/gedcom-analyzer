"""
Findet wahrscheinlich ungenutzte Imports
"""
import subprocess
import re
from pathlib import Path

unused = []

for py_file in Path("ancestry").rglob("*.py"):
    with open(py_file) as f:
        content = f.read()
    
    # Find imports
    imports = re.findall(r'^(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_\.]*)', content, re.MULTILINE)
    
    for imp in imports:
        # Get the base name (last part)
        base = imp.split('.')[-1]
        
        # Check if it's used in the file (excluding the import line itself)
        lines = content.split('\n')
        import_line_num = None
        
        for i, line in enumerate(lines):
            if f"import {imp}" in line or f"from {imp}" in line:
                import_line_num = i
                break
        
        if import_line_num is not None:
            rest_content = '\n'.join(lines[import_line_num+1:])
            
            # Check if base name is used
            if not re.search(rf'\b{re.escape(base)}\b', rest_content):
                unused.append((str(py_file), imp, import_line_num + 1))

print(f"Potentially unused imports (first 30):")
print("=" * 70)
for fpath, imp, line in unused[:30]:
    print(f"  {fpath}:{line}  import {imp}")

if len(unused) > 30:
    print(f"  ... and {len(unused) - 30} more")
