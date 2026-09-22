import json
from pathlib import Path

def test_mcp_config_schema():
    config_file = Path(".agents/mcp_config.json")
    assert config_file.exists(), "File .agents/mcp_config.json phải tồn tại"
    
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "mcpServers" in data
    assert "notebooklm" in data["mcpServers"]
    nlm_cfg = data["mcpServers"]["notebooklm"]
    assert "command" in nlm_cfg
    assert "args" in nlm_cfg
    assert nlm_cfg["args"] == ["mcp"]
