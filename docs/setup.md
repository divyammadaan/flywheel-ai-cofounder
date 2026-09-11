# Setup

## Installing dependencies

`pip install -r requirements.txt` in one shot fails: pip's resolver hits
`resolution-too-deep` trying to jointly solve `crewai` + `google-adk` +
`a2a-sdk` + `chromadb` — their transitive dependency trees (esp.
`google-adk`'s google-cloud-* stack) are large enough that combined
resolution blows past pip's search depth.

Install in stages instead, so each pip invocation resolves a smaller graph:

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install --upgrade pip
pip install crewai
pip install google-adk
pip install mcp a2a-sdk
pip install ollama groq google-generativeai
pip install fastapi uvicorn python-dotenv pydantic
pip install chromadb
pip install streamlit
pip install pytest
```

If a later stage still backtracks badly, pin the offending package to a
specific version (`pip index versions <pkg>` to see choices) rather than
letting pip search the whole history.
