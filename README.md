# LLM-Based Code Refactoring Benchmark (Bachelor Thesis)

This repository contains the code and artifacts used for my bachelor thesis on **LLM-based code refactoring**. It includes the refactoring task definitions, experiment scripts, and the evaluation/validation pipeline used to measure success rates across different projects and programming languages.

## Project Overview
The main goal is to evaluate how reliably different LLMs can apply refactorings to real-world code while preserving behavior.

**Key ideas:**
- Run multiple iterations per refactoring task
- Validate results with regression tests (and manual checks for certain refactorings)
- Compare outcomes across refactoring types, project complexity, and language

## Repository Structure

- **`prompts_apex-dml-mocking/`**  
  Refactoring task prompts for the Apex DML Mocking project, including:
  - `coc_reduktion.txt` – Cyclomatic complexity reduction
  - `getter_setter.txt` – Generate getters/setters
  - `guard_clauses.txt` – Extract guard clauses
  - `inline_variable.txt` – Inline variable refactoring
  - `rename.txt` – Rename refactoring
  - `strategy_pattern.txt` – Strategy pattern extraction

- **`prompts_pathlib2_testing/`**  
  Refactoring task prompts for the pathlib2 Python project (same refactoring types as above)

- **`refactoring_apex.py`**  
  Automation script to execute Apex refactoring experiments

- **`refactoring_python.py`**  
  Automation script to execute Python refactoring experiments

- **`run_refactored_pytest.py`**  
  Utility to run pytest validation on refactored Python code

## Requirements
- Python `3.x` (for orchestration scripts)
- Salesforce CLI (for Apex validation and test execution)
- Access to the LLM(s) used in the experiments (API keys or local model setup)
- pytest (for Python validation)

## Setup

```bash
git clone https://github.com/Ronald-Nguyen/bachelor-thesis-llm-complexity
cd bachelor-thesis-llm-complexity

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

### 1. Configure Project Paths
**Important:** Before running experiments, you must edit the path variables in the refactoring scripts to point to your local project directories.

**In `refactoring_apex.py`:**
```python
PATH = 'force-app'  # Edit this to point to your Apex project directory
```

**In `refactoring_python.py`:**
```python
PATH = 'src/pathlib2'  # Edit this to point to your Python project directory
```

**In `run_refactored_pytest.py`:**
```python
PROJECT_SRC_PATH = Path("src/pathlib2")  # Edit this to match your Python project path
```

### 2. Set Up API Keys
Configure environment variables for the LLM APIs you plan to use:

```bash
# Windows (PowerShell)
$env:GROQ_API_KEY = "your-groq-api-key"
$env:GEMINI_API_KEY = "your-gemini-api-key"
$env:MISTRAL_API_KEY2 = "your-mistral-api-key"

# Linux/macOS
export GROQ_API_KEY="your-groq-api-key"
export GEMINI_API_KEY="your-gemini-api-key"
export MISTRAL_API_KEY2="your-mistral-api-key"
```

### 3. Set Up Test Projects
Clone or copy the test projects into your workspace:

- **apex-dml-mocking**: Apex/Salesforce project for Apex refactoring experiments
- **pathlib2**: Python project for Python refactoring experiments

### 4. Salesforce Setup (For Apex Experiments)
Before running Apex refactoring experiments, you need to set up a Salesforce scratch org:

**Step 1: Login to your Dev Hub**
```powershell
sf org login web --set-default-dev-hub --alias MeinDevHub
```

**Step 2: Delete old scratch org (if exists)**
```powershell
sf org delete scratch --target-org MyTestOrg --no-prompt
```

**Step 3: Create new scratch org**
```powershell
sf org create scratch --set-default --definition-file config/project-scratch-def.json --alias MyTestOrg --duration-days 1
```

**Note:** Make sure you have a `config/project-scratch-def.json` file in your Apex project directory before creating the scratch org.

### 5. Output Directories
The scripts automatically create output directories when you run experiments. Each refactoring run creates its own directory named `<refactoring_name>_result_<model_name>/` (Apex) or `<refactoring_name>_results_<model_name>/` (Python).

## Running the Experiments

### 1) Execute Apex refactoring runs
```bash
python refactoring_apex.py --model <MODEL_NAME> --runs 10
```

### 2) Execute Python refactoring runs
```bash
python refactoring_python.py --model <MODEL_NAME> --runs 10
```

### 3) Validate Python results with pytest
```bash
python run_refactored_pytest.py --input results/raw
```

## Validation Approach (High Level)
A run is considered **functionally correct** if all regression tests pass after the refactoring.

Some refactoring types additionally require **manual or structural validation** (e.g., strategy pattern extraction, guard clause structure), because tests alone do not always confirm that the intended refactoring was applied.

**Two test projects evaluated:**
- **apex-dml-mocking** (Apex/Salesforce)
- **pathlib2** (Python)

## Getting Started Checklist

Before running your first experiment, make sure you have:

- [x] Cloned this repository
- [ ] Created and activated a Python virtual environment
- [ ] Installed dependencies (`pip install -r requirements.txt`)
- [ ] Edited `PATH` variables in `refactoring_apex.py` and `refactoring_python.py`
- [ ] Edited `PROJECT_SRC_PATH` in `run_refactored_pytest.py`
- [ ] Set up LLM API keys as environment variables
- [ ] Cloned/copied test projects (apex-dml-mocking, pathlib2) into your workspace
- [ ] (For Apex) Installed Salesforce CLI (`sf` command available)
- [ ] (For Apex) Logged in to Dev Hub (`sf org login web --set-default-dev-hub`)
- [ ] (For Apex) Created scratch org with `config/project-scratch-def.json`
- [ ] Verified test projects run successfully before refactoring
  - Python: `cd pathlib2 && pytest`
  - Apex: `sf apex test run` in your project directory

## Data and Outputs

### Apex Refactoring Results
Results are stored in directories named: `<refactoring_name>_result_<model_name>/`

Example: `coc_reduktion_result_gemini-3-pro-preview/`

Each refactoring directory contains:
- `iteration_01/`, `iteration_02/`, etc. — Results for each iteration
- `<model_name>_summary_results.txt` — Aggregated summary across all iterations

Each iteration directory contains:
- `code/` — Refactored source files
- `success_test_result.txt` or `failure_test_result.txt` — Test execution results
- `ai_response.txt` — Raw LLM response
- `diff.txt` — Diff between original and refactored code

### Python Refactoring Results
Results are stored in directories named: `<refactoring_name>_results_<model_name>/`

Example: `inline_variable_results_llama-3.3-70b-versatile/`

Structure is the same as Apex results above.

### Pytest Validation Results
When running `run_refactored_pytest.py`, validation reports are stored in: `test_results/`

## Reproducibility Notes
- Exact results may vary due to LLM non-determinism.
- If you use temperature > 0 or non-fixed seeds, reruns can differ.
- Environment differences (dependencies, test runtimes, Apex org setup) can affect outcomes.

## License
All rights reserved.
