import ast
import glob
import os
import re

mixin_files = glob.glob('/Users/davidhona/dev/franklinwh-cloud/franklinwh_cloud/mixins/*.py')
client_file = '/Users/davidhona/dev/franklinwh-cloud/franklinwh_cloud/client.py'

all_files = mixin_files + [client_file]

markdown = []
markdown.append("# FranklinWH API Endpoints Mapping\n")
markdown.append("A complete mapping of the internal `franklinwh-cloud` Python methods to their corresponding Cloud API HTTP endpoints.\n")
markdown.append("> 💡 **Note**: For code examples and tutorials on how to use these methods in your scripts, see the [API Cookbook](API_COOKBOOK.md) and [API Reference](API_REFERENCE.md).\n")

for filepath in sorted(all_files):
    if '__init__' in filepath: continue
    
    filename = os.path.basename(filepath)
    category = filename.replace('.py', '').title()
    if category == 'Client':
        category = 'Core Client & Auth'
        
    markdown.append(f"\n## {category}\n")
    markdown.append("| Python Method | Arguments | HTTP | Cloud API Endpoint | Cookbook Sample |")
    markdown.append("|---------------|-----------|------|--------------------|-----------------|")
    
    with open(filepath, 'r') as f:
        source = f.read()
        
    tree = ast.parse(source)
    methods_found = False
    
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
            if node.name.startswith('_') and node.name != '__init__':
                continue
                
            args = [a.arg for a in node.args.args if a.arg != 'self']
            args_str = ", ".join(args)
            if not args_str:
                args_str = "—"
            else:
                args_str = f"`{args_str}`"
                
            http_method = "N/A"
            endpoint = "N/A"
            
            # Find _get or _post
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Attribute) and child.func.attr in ('_get', '_post', '_request'):
                        http_method = "GET" if child.func.attr == '_get' else "POST"
                        if child.args:
                            arg0 = child.args[0]
                            # Try to extract the string
                            if isinstance(arg0, ast.Constant):
                                endpoint = str(arg0.value)
                            elif isinstance(arg0, ast.JoinedStr):
                                parts = []
                                for v in arg0.values:
                                    if isinstance(v, ast.Constant):
                                        parts.append(str(v.value))
                                    elif isinstance(v, ast.FormattedValue):
                                        val = ast.unparse(v.value)
                                        # Cleanup common self refs
                                        val = val.replace('self.gateway', '{gateway_id}')
                                        val = val.replace('self.', '')
                                        parts.append(f"{{{val}}}")
                                endpoint = "".join(parts)
                            elif isinstance(arg0, ast.BinOp):
                                if isinstance(arg0.right, ast.Constant):
                                    endpoint = str(arg0.right.value)
                                elif isinstance(arg0, ast.JoinedStr):
                                    parts = []
                                    for v in arg0.right.values:
                                        if isinstance(v, ast.Constant):
                                            parts.append(str(v.value))
                                        elif isinstance(v, ast.FormattedValue):
                                            parts.append(f"{{{ast.unparse(v.value)}}}")
                                    endpoint = "".join(parts)
                                elif isinstance(arg0.left, ast.Constant):
                                    endpoint = str(arg0.left.value)
                            elif isinstance(arg0, ast.Name):
                                # It's a variable like `url`, very hard to trace dynamically in AST without flow
                                endpoint = "{dynamic_url}"
            
            # Cleanup endpoint
            if endpoint != "N/A":
                endpoint = endpoint.replace('hes-gateway/', '/hes-gateway/')
                endpoint = re.sub(r'//hes-gateway', r'/hes-gateway', endpoint)
                if not endpoint.startswith('/'):
                    endpoint = '/' + endpoint
            
            if endpoint != "N/A":
                # Find cookbook reference anchor
                # Guess an anchor based on module name
                anchor = f"[View Examples](API_COOKBOOK.md)"
                
                markdown.append(f"| `{node.name}()` | {args_str} | {http_method} | `{endpoint}` | {anchor} |")
                methods_found = True

    if not methods_found:
        markdown.pop()
        markdown.pop()
        markdown.pop()
        markdown.pop()

with open('/Users/davidhona/dev/franklinwh-cloud/docs/API_ENDPOINTS_MAPPING.md', 'w') as f:
    f.write("\n".join(markdown))
    f.write("\n")
