import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

# Test 1: package imports
try:
    import src
    import src.model
    import src.core
    import src.io
    import src.detector
    import src.agent
    import src.verifier
    import src.utils
    results.append(("package imports", "OK", "all 8 packages importable"))
except Exception as e:
    errors.append(("package imports", str(e)))

# Test 2: ip_config exists and parseable
ip_path = "ip_config"
if os.path.exists(ip_path):
    config = {}
    with open(ip_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip()
    base_url = config.get("OLLAMA_BASE_URL", "")
    model_name = config.get("OLLAMA_MODEL", "")
    if base_url and model_name:
        results.append(("ip_config", "OK", f"base_url={base_url}, model={model_name}"))
    else:
        errors.append(("ip_config", "missing OLLAMA_BASE_URL or OLLAMA_MODEL"))
else:
    errors.append(("ip_config", "file not found"))

# Test 3: .gitignore exists
if os.path.exists(".gitignore"):
    content = open(".gitignore", encoding="utf-8").read()
    checks = ["ip_config" in content, "__pycache__" in content, ".checkpoint" in content]
    results.append((".gitignore", "OK" if all(checks) else "WARN",
                    f"excludes ip_config, __pycache__, .checkpoint: {all(checks)}"))
else:
    errors.append((".gitignore", "file not found"))

# Test 4: requirements.txt exists
if os.path.exists("requirements.txt"):
    results.append(("requirements.txt", "OK", "exists"))
else:
    errors.append(("requirements.txt", "file not found"))

# Test 5: README.md exists
if os.path.exists("README.md"):
    results.append(("README.md", "OK", "exists"))
else:
    errors.append(("README.md", "file not found"))

# Test 6: Git initialized
if os.path.isdir(".git"):
    results.append(("git init", "OK", "git repository initialized"))
else:
    errors.append(("git init", "no .git directory"))

# Test 7: Git remote configured
r = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True,
                   cwd=os.path.dirname(os.path.abspath(__file__)))
if r.stdout.strip():
    results.append(("git remote", "OK", r.stdout.strip().split("\n")[0]))
else:
    errors.append(("git remote", "no remote configured"))

# Test 8: Data files exist
novel_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ori_story")
if os.path.isdir(novel_dir):
    novels = [f for f in os.listdir(novel_dir) if f.endswith(".txt")]
    results.append(("data/ori_story", "OK", f"{len(novels)} novel files"))
else:
    errors.append(("data/ori_story", "directory not found"))

# Print results
print("=" * 55)
print("  Stage 1 Verification Report")
print("=" * 55)
for name, status, detail in results:
    mark = "[OK]" if status == "OK" else "[!!]"
    print(f"  {mark} {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
