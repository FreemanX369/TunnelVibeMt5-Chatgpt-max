from pathlib import Path
import json, sys, types
assert not any(name.startswith("mcp") for name in sys.modules)
fake=types.ModuleType("mcp.server.mcpserver")
fake.MCPServer=type("MCPServer",(),{})
fake.Context=type("Context",(),{})
for name,module in (("mcp",types.ModuleType("mcp")),("mcp.server",types.ModuleType("mcp.server")),("mcp.server.mcpserver",fake)):
    sys.modules[name]=module
from vibemql5.adapters.mcp import create_server
try:
    create_server(Path("owned-unused-root"), transport="stdio")
except RuntimeError as error:
    assert str(error)=='MCP SDK v2 is required. Run: pip install -e ".[mcp]"'
    assert type(error.__cause__) is ModuleNotFoundError
    assert error.__cause__.name=="mcp.server.mcpserver.exceptions"
    print(json.dumps({"scope":"incomplete-stub-strict-import-control","strict_sdk_error_preserved":True,"error":str(error),"cause":str(error.__cause__),"exception_module_loaded":"mcp.server.mcpserver.exceptions" in sys.modules}))
else:
    raise AssertionError("Strict SDK import must fail")
