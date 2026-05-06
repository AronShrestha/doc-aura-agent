# 🧠 Doc AURA — Product Requirements Document (PRD)
### “Documentation as a byproduct of code changes”

---

# 1. 🎯 Vision

Build a **living documentation system** that automatically stays in sync with the codebase.

> Documentation should not be a task. It should be a **side-effect of development**.

---

# 2. 🚨 Problem Statement

Fast-moving engineering teams face:

- Documentation becomes outdated after every PR
- Developers stop trusting docs
- Onboarding slows down
- Knowledge becomes tribal
- Bugs increase due to misunderstandings

> Current tools generate docs once. They do not **maintain** them.

---

# 3. 💡 Solution

Doc AURA continuously:

- Understands the codebase structure
- Generates high-signal documentation
- Detects code changes (PRs)
- Updates only impacted documentation
- Shows **documentation diffs (like code diffs)**
- Highlights change impact across the system

---

# 4. 👤 Target Users (ICP)

- Startup engineering teams with high PR velocity (10–100 PRs/week)
- Open-source maintainers
- Backend/API-heavy teams

---

# 5. 🧩 Core Features

## 5.1 Codebase Understanding Engine
- Parses repository
- Builds structured code graph (modules, APIs, dependencies)

---

## 5.2 Documentation Generator
Generates **high-signal structured documentation**:

- Project Overview
- Architecture Overview
- API Reference
- Key Workflows
- Usage Examples

---

## 5.3 Change Detection Engine
- Tracks PRs / commits
- Identifies changed files
- Maps changes to system components

---

## 5.4 Documentation Sync Engine (Core Differentiator)
- Updates only impacted documentation
- Avoids full regeneration
- Maintains consistency

---

## 5.5 Documentation Diff
- Shows:
  - Added docs
  - Modified docs
  - Removed docs
- Side-by-side comparison

---

## 5.6 Change Impact Summary
- What changed
- Affected modules
- Affected APIs
- Behavioral impact

---

## 5.7 PR Review Assistant
- Flags:
  - Undocumented changes
  - Mismatched docs
- Adds comments to PRs

---

## 5.8 Interactive Code Graph
- Visual representation of system
- Click → explore docs
- Highlights PR impact
- Supports workflow tracing

---

## 5.9 Architecture Diagram Generator
- Auto-generates system diagrams
- Updates based on code changes

---

# 6. 🏗️ System Architecture (High-Level)

### Components:

1. **Repo Analyzer**
   - Parses code (AST)
   - Builds code graph

2. **Doc Generator**
   - Creates structured documentation

3. **Change Detector**
   - Processes PR diffs

4. **Doc Sync Engine**
   - Updates affected docs

5. **Reviewer Agent**
   - PR feedback

6. **Graph Engine**
   - Builds interactive graph

7. **Frontend Dashboard**
   - Displays docs, diffs, graph

---

# 7. ⚙️ Tech Stack

### Backend
- FastAPI
- Python
- Tree-sitter (code parsing)

### AI / Orchestration
- LLM APIs (OpenAI / local models)
- LangGraph (agent workflows)

### Frontend
- React
- React Flow (interactive graph)

### Storage
- JSON (structured docs)
- Optional: SQLite / lightweight DB

---

# 8. 🔄 Core Workflow

## Initial Setup
1. User connects GitHub repo
2. System analyzes codebase
3. Generates structured documentation
4. Builds code graph + diagrams

---

## PR Flow
1. PR detected
2. Code diff analyzed
3. Impacted components identified
4. Documentation updated
5. Diff generated
6. Graph updated (highlight changes)
7. PR comments generated

---

# 9. 🧪 Demo Plan (CRITICAL FOR WINNING)

## Demo Story (must be tight, <3 mins)

### Step 1 — Import Repo
- Show generated documentation dashboard

---

### Step 2 — Show Architecture
- Display architecture diagram
- Show interactive graph

---

### Step 3 — Introduce PR
- Add new endpoint / modify logic

---

### Step 4 — System Reaction (WOW MOMENT)
- Highlight impacted components in graph
- Show:
  - Change impact summary
  - Updated documentation
  - **Documentation diff**

---

### Step 5 — PR Review
- Show automated comment:
  - “New endpoint is undocumented”
  - “Behavior changed”

---

> 🎯 Key Moment: **Doc Diff + Graph Highlight together**

---

# 10. 🏆 Hackathon Winning Strategy

## 10.1 What Judges Care About

- Clear problem → solution mapping
- Strong differentiation
- Clean demo (not complexity)
- Real-world applicability
- Technical credibility

---

## 10.2 Your Differentiation

Most tools:
> Generate documentation

Doc AURA:
> **Maintains documentation continuously and shows change impact**

---

## 10.3 Must-Have to Win

- 🔥 Documentation Diff (core innovation)
- 🔥 PR Impact Visualization (graph)
- 🔥 Clean UI (not cluttered)
- 🔥 Real repo demo (not toy)

---

## 10.4 Avoid These Mistakes

- Overloading with features
- Showing too many agents
- Generating low-quality docs
- Slow or broken demo
- No clear “wow moment”

---

## 10.5 Pitch (15-second)

> “Documentation breaks in fast-moving teams because it becomes outdated after every PR.  
We built a system where documentation updates automatically with code changes.  
Every pull request generates a documentation diff, so teams can review not just code, but how the system is explained.  
Docs become a byproduct of development — not a separate task.”

---

# 11. 📊 Success Metrics

- Accuracy of generated docs
- Correct detection of impacted components
- Quality of documentation diff
- Demo clarity and speed

---

# 12. 🚀 MVP Scope (Strict)

Focus only on:

- API Reference
- Architecture Overview
- Key Workflows
- Change Impact Summary
- Documentation Diff
- Interactive Graph (basic)

---

# 13. 🔮 Future Scope (Post-hackathon)

- Multi-language support
- IDE integration
- CI/CD integration
- Team collaboration features
- Versioned documentation

---

# 14. 🧠 Key Insight

> The value is not in generating documentation.

> The value is in **keeping it correct over time**.

---

# 15. 📌 Final Positioning

Doc AURA is:

- Not a documentation generator  
- Not a static tool  

It is:

> **A continuous documentation system that evolves with your codebase**