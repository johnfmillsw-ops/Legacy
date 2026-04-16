# Legacy

**AI-powered personality and memory preservation system.**

Legacy creates an interactive digital version of a person — preserving their stories, values, wisdom, and personality so others can ask questions and receive guidance in their authentic voice.

Built as both a **CLI tool** and a **Flask web app**, it uses small language models, RAG (retrieval-augmented generation), and local storage — no cloud dependency required.

### Features
- Interview mode to capture life stories, values, and guidance
- Upload personal summaries or documents for AI extraction
- Guidance mode — ask questions and get responses in the person's voice
- Core summary generation with GPT-4o-mini (optional)
- Fully local-first (data stored in `/data` as JSON)
- Web dashboard + CLI interface

### Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/johnfmillsw-ops/Legacy.git
cd Legacy

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your OpenAI key (optional but recommended)
export OPENAI_API_KEY=sk-...

# 4. Run the CLI version
python src/main.py

# 5. Or run the web version
python src/webapp.py
