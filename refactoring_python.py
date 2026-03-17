import os
from pyexpat import model
import re
import shutil
import argparse
import difflib
import subprocess  # nosec
import time
from pathlib import Path
from datetime import datetime
from unittest import result

"""
python refactorings/refactoring.py
python refactorings/refactoring.py --all-refactorings
python refactorings/refactoring.py --refactoring inline_variable
"""

REFACTORINGS = [
    "coc_reduktion",
    "getter_setter",
    "guard_clauses",
    "inline_variable",
    "rename",
    "strategy_pattern",
]
DEFAULT_REFACTORING = "getter_setter"
RESULT_PATH = "_results_"
PATH = 'src/pathlib2'
ITERATIONS = 10
GEMINI3 = 'gemini-3-pro-preview'
GEMINI2 = 'gemini-2.5-flash'
LLAMA = 'llama-3.3-70b-versatile'
MISTRAL = 'mistral-large-2512'
CODESTRAL = 'codestral-2501'
MODEL_OLLAMA = 'devstral-2_123b-cloud'
MODEL_GROQ = LLAMA
MODEL_GEMINI = GEMINI3
MODEL_MISTRAL = CODESTRAL
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY')
LLM_API_KEY = GEMINI_API_KEY
client = None
MODEL = None

if LLM_API_KEY == MISTRAL_API_KEY:
    from mistralai import Mistral
    MODEL = MODEL_MISTRAL
    try:
        client = Mistral(api_key=LLM_API_KEY)
        print("Mistral API Key aus Umgebungsvariable geladen")
    except Exception as e:
        print(f"Fehler beim Laden des API-Keys: {e}")
        exit(1)    
elif LLM_API_KEY == GEMINI_API_KEY:
    from google import genai
    MODEL = MODEL_GEMINI
    try:
        client = genai.Client(api_key=LLM_API_KEY)
        print("Gemini API Key aus Umgebungsvariable geladen")
    except Exception as e:
        print(f"Fehler beim Laden des API-Keys: {e}")
        exit(1)
elif LLM_API_KEY == GROQ_API_KEY:
    from groq import Groq
    MODEL = MODEL_GROQ
    try:
        client = Groq(api_key=LLM_API_KEY)
        print("Groq API Key aus Umgebungsvariable geladen")
    except Exception as e:
        print(f"Fehler beim Laden des API-Keys: {e}")
        exit(1)




parser = argparse.ArgumentParser(description="Projektpfad angeben")
parser.add_argument("--project-path", type=str, default=PATH, help="Pfad des Projekts")
parser.add_argument(
    "--all-refactorings",
    action="store_true",
    help="Wenn gesetzt: führt alle Refactorings nacheinander aus.",
)
parser.add_argument(
    "--refactoring",
    type=str,
    default=DEFAULT_REFACTORING,
    choices=REFACTORINGS,
    help="Welches Refactoring ausgeführt werden soll (wenn --all-refactorings nicht gesetzt ist).",
)
args = parser.parse_args()

PROJECT_DIR = Path(args.project_path)

def get_project_structure(project_dir: Path) -> str:
    """Erstellt eine Übersicht der Projektstruktur."""
    structure = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'__pycache__', 'tests', 'pathlib2.egg-info'}]
        level = root.replace(str(project_dir), '').count(os.sep)
        indent = ' ' * 2 * level
        structure.append(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            if file.endswith('.py'):
                structure.append(f'{subindent}{file}')
    return '\n'.join(structure)

def get_all_python_files(project_dir: Path) -> str:
    """Liest alle Python-Dateien ein und liefert einen großen Textblock."""
    code_block = ""
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'__pycache__', 'tests', 'pathlib2.egg-info'}]
        for file in files:
            if "test" in file:
                continue
            if file.endswith('.py'):
                file_path = Path(root) / file
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    relative_path = file_path.relative_to(project_dir)
                    code_block += f"\n\nFile `{relative_path}`:\n```python\n"
                    code_block += content + "```\n"
                except Exception as e:
                    print(f"Fehler beim Lesen von {file_path}: {e}")
    return code_block

def parse_ai_response(response_text: str) -> dict:
    """Parst die AI-Antwort und extrahiert Dateinamen und Code."""
    files = {}
    pattern = r"File\s+`([^`]+)`:\s*```python\s*(.*?)\s*```"
    matches = re.findall(pattern, response_text, re.DOTALL)
    for filename, code in matches:
        files[filename] = code.strip()
    return files

def backup_project(project_dir: Path, backup_dir: Path) -> None:
    """Erstellt ein Backup des Projekts."""
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(
        project_dir, backup_dir, 
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 'test', 'tests', 'pathlib2.egg-info')
    )

def restore_project(backup_dir: Path, project_dir: Path) -> None:
    """Stellt das Projekt aus dem Backup wieder her"""
    backup_dir = Path(backup_dir).resolve()
    project_dir = Path(project_dir).resolve()

    if not backup_dir.exists():
        raise FileNotFoundError(f"Backup-Verzeichnis nicht gefunden: {backup_dir}")

    project_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(backup_dir, project_dir, dirs_exist_ok=True)

def apply_changes(project_dir: Path | str, files: dict[str, str]) -> dict:
    """Wendet die Änderungen auf die Dateien an, ignoriert jedoch Dateien im 'tests'-Ordner."""
    project_dir = Path(project_dir).resolve()
    written: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for filename, code in files.items():
        file_rel = Path(filename)

        if any(part == 'tests' for part in file_rel.parts):
            skipped.append(filename)
            continue

        file_path = (project_dir / file_rel).resolve()
        try:
            file_path.relative_to(project_dir)
        except ValueError:
            msg = f" {filename} liegt außerhalb von {project_dir}, übersprungen"
            print(msg)
            skipped.append(filename)
            errors.append(msg)
            continue

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(code, encoding='utf-8')
            print(f" {filename} aktualisiert")
            written.append(filename)
        except Exception as e:
            msg = f" Fehler beim Schreiben von {filename}: {e}"
            print(msg)
            errors.append(msg)

    return {
        "written": written,
        "skipped": skipped,
        "errors": errors,
        "written_count": len(written),
    }

def _read_text_best_effort(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

def _normalize_lines_ignore_whitespace_and_blanklines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for line in text.split("\n"):
        normalized = re.sub(r"\s+", "", line)
        if normalized == "":
            continue
        out.append(normalized)
    return out

def build_diff_between_backup_and_refactored(
    backup_dir: Path,
    project_src: Path,
    snapshot_files: dict[str, str],
) -> tuple[bool, str]:
    diffs: list[str] = []
    has_changes = False

    rel_paths = sorted({str(Path(p)) for p in snapshot_files.keys()})
    for rel in rel_paths:
        rel_path = Path(rel)

        if any(part in {"tests", "test"} for part in rel_path.parts):
            continue

        orig_path = backup_dir / rel_path
        new_path = project_src / rel_path

        orig_text = _read_text_best_effort(orig_path) if orig_path.exists() else ""
        new_text = _read_text_best_effort(new_path) if new_path.exists() else ""

        orig_norm = _normalize_lines_ignore_whitespace_and_blanklines(orig_text)
        new_norm = _normalize_lines_ignore_whitespace_and_blanklines(new_text)

        if orig_norm == new_norm:
            continue

        has_changes = True
        diff_lines = list(
            difflib.unified_diff(
                orig_norm,
                new_norm,
                fromfile=f"backup/{rel}",
                tofile=f"refactored/{rel}",
                lineterm="",
                n=0,
            )
        )
        if diff_lines:
            diffs.append("\n".join(diff_lines))

    return has_changes, ("\n\n".join(diffs)).strip()

def run_pytest():
    """Führt pytest aus und gibt das Ergebnis zurück."""
    try:
        result = subprocess.run(  # nosec
            ['pytest'], 
            capture_output=True, 
            text=True, 
        )
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
    except Exception as e:
        return {'success': False, 'stdout': '', 'stderr': str(e), 'returncode': -1}

def save_results(
    iteration: int,
    result_dir: Path,
    files: dict,
    test_result: dict,
    response_text: str,
    diff_text: str,
) -> None:
    """Speichert die Ergebnisse einer Iteration."""
    result_dir.mkdir(parents=True, exist_ok=True)
    code_dir = result_dir / "code"
    code_dir.mkdir(exist_ok=True)
    for filename, code in files.items():
        file_path = code_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)

    if(test_result['success']):
        status = "success_"
    else:
        status = "failure_"
    with open(result_dir / f"{status}test_result.txt", 'w', encoding='utf-8') as f:
        f.write(f"Iteration {iteration}\nTimestamp: {datetime.now().isoformat()}\n")
        f.write(f"Success: {test_result['success']}\n")
        f.write("\n" + "="*60 + "\nSTDOUT:\n" + test_result['stdout'])
        f.write("\n" + "="*60 + "\nSTDERR:\n" + test_result['stderr'])

    with open(result_dir / "ai_response.txt", 'w', encoding='utf-8') as f:
        f.write(response_text)

    with open(result_dir / "diff.txt", 'w', encoding='utf-8') as f:
        f.write(diff_text or "")

def write_summary(results_dir: Path, text: str) -> None:
    with open(results_dir / f"{MODEL}_summary_results.txt", "a", encoding="utf-8") as f:
        f.write(text)

def _usage_to_dict(usage) -> dict | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    data = {}
    for attr in ("prompt_tokens", "completion_tokens", "total_tokens",
                 "prompt_token_count", "candidates_token_count", "total_token_count"):
        if hasattr(usage, attr):
            data[attr] = getattr(usage, attr)
    return data or None

def format_token_usage(usage: dict | None) -> str:
    if not usage:
        return "Tokens: n/a"
    prompt = usage.get("prompt_tokens", usage.get("prompt_token_count"))
    completion = usage.get("completion_tokens", usage.get("candidates_token_count"))
    total = usage.get("total_tokens", usage.get("total_token_count"))
    parts = []
    if prompt is not None:
        parts.append(f"prompt={prompt}")
    if completion is not None:
        parts.append(f"completion={completion}")
    if total is not None:
        parts.append(f"total={total}")
    if not parts:
        return "Tokens: n/a"
    return "Tokens: " + ", ".join(parts)

def groq_generate(final_prompt: str) -> tuple[str, dict | None]:
    resp = client.chat.completions.create(
        model=MODEL,
        content=final_prompt
    )
    usage = _usage_to_dict(getattr(resp, "usage", None))
    return resp.choices[0].message.content, usage

def gemini_generate(final_prompt: str) -> tuple[str, dict | None]:
    """Fragt Gemini (Text Completions) an und gibt den Text-Content zurück."""
    response = client.models.generate_content(
        model=MODEL,
        contents=final_prompt
    )

    response_text = getattr(response, "text", None)
    if not response_text and hasattr(response, "candidates"):
        parts = [p.text for c in response.candidates for p in c.content.parts if hasattr(p, "text")]
        response_text = "\n".join(parts)
    
    if not response_text:
        raise ValueError("Leere Antwort erhalten")

    usage = None
    usage_meta = getattr(response, "usage_metadata", None)
    if usage_meta is not None:
        usage = _usage_to_dict(usage_meta)

    return response_text, usage

def mistral_generate(prompt: str) -> tuple[str, dict | None]:
    res = client.chat.complete(
        model=MODEL,
        messages=[
            {
                "content": prompt,
                "role": "user",
            },
        ],
        temperature=0.2,
        stream=False
    )
    usage = _usage_to_dict(getattr(res, "usage", None))
    return res.choices[0].message.content, usage

def main():
    if args.all_refactorings:
        selected_refactorings = REFACTORINGS
    else:
        selected_refactorings = [args.refactoring]

    print(f"{'='*60}\nStarte Refactoring-Experiment\n{'='*60}\n")

    backup_dir = Path("backup_original")
    backup_project(PROJECT_DIR, backup_dir)

    for ref_name in selected_refactorings:
        prompt_path = Path(f"{ref_name}.txt")
        if not prompt_path.exists():
            print(f"Fehler: Prompt nicht gefunden: {prompt_path}")
            continue

        your_prompt = prompt_path.read_text(encoding='utf-8')
        results_dir = Path(ref_name + RESULT_PATH + MODEL)
        results_dir.mkdir(exist_ok=True)

        print(f"{'='*60}\nRefactoring: {ref_name}\n{'='*60}\n")

        project_structure = get_project_structure(PROJECT_DIR)
        code_block = get_all_python_files(PROJECT_DIR)

        final_prompt = f"{your_prompt}\n\nStructure:\n{project_structure}\n\nCode:\n{code_block}"
        successful_iterations = 0
        test_passes = 0
        diff_passes = 0
        ref_passes = 0

        with open(results_dir / "full_prompt.txt", "w", encoding="utf-8") as f:
            f.write(final_prompt)

        for i in range(1, ITERATIONS + 1):
            print(f"\nITERATION {i}/{ITERATIONS}")
            restore_project(backup_dir, PROJECT_DIR)

            try:
                usage = None
                if LLM_API_KEY == MISTRAL_API_KEY:
                    response_text, usage = mistral_generate(final_prompt)
                elif LLM_API_KEY == GEMINI_API_KEY:
                    response_text, usage = gemini_generate(final_prompt)
                elif LLM_API_KEY == GROQ_API_KEY:
                    response_text, usage = groq_generate(final_prompt)

                files = parse_ai_response(response_text)
                if not files:
                    write_summary(results_dir, f"iteration {i} failed test failed diff failed ref failed Tokens: n/a\n")
                    continue

                apply_stats = apply_changes(PROJECT_DIR, files)

                has_diff, diff_text = build_diff_between_backup_and_refactored(
                    backup_dir=backup_dir,
                    project_src=PROJECT_DIR,
                    snapshot_files=files,
                )
                diff_status = "passed" if has_diff else "failed"

                test_result = run_pytest()
                test_status = "passed" if test_result.get("success") else "failed"

                ref_ok = bool(apply_stats.get("written_count", 0)) > 0
                ref_status = "passed" if ref_ok else "failed"

                token_info = format_token_usage(usage)

                if test_result['success'] and has_diff and ref_ok:
                    successful_iterations += 1

                if test_result.get("success"):
                    test_passes += 1
                if has_diff:
                    diff_passes += 1
                if ref_ok:
                    ref_passes += 1

                iteration_status = "passed" if (test_result.get("success") and has_diff and ref_ok) else "failed"
                line = (
                    f"iteration {i} {iteration_status} "
                    f"test {test_status} diff {diff_status} ref {ref_status} {token_info}\n"
                )
                write_summary(results_dir, line)
                print(line.strip())

                save_results(i, results_dir / f"iteration_{i:02d}", files, test_result, response_text, diff_text)

            except Exception as e:
                print(f"Fehler: {e}")
                print("Warte 60 Sekunden vor nächstem Versuch...")
                time.sleep(60)

        success_rate = successful_iterations / ITERATIONS * 100 if ITERATIONS else 0.0
        overall_line = (
            f"Fertig. Erfolgsrate: {success_rate:.1f}% ({successful_iterations}/{ITERATIONS}) "
            f"test_pass={test_passes}/{ITERATIONS} diff_pass={diff_passes}/{ITERATIONS} "
            f"ref_pass={ref_passes}/{ITERATIONS}\n"
        )
        print("\n" + overall_line.strip())
        write_summary(results_dir, overall_line)

    restore_project(backup_dir, PROJECT_DIR)

if __name__ == "__main__":
    main()
