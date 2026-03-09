import argparse
import os
import re
import shutil
import subprocess
import difflib
from datetime import datetime
from pathlib import Path

PROJECT_SRC_PATH = Path("src/pathlib2")
REFACTORING_BASE_PATH = Path("refactoring")
TEST_RESULTS_BASE = Path("test_results")

ITERATION_PREFIX = "iteration_"
SUMMARY_FILENAME = "test_results.txt"
ITERATION_RESULT_FILENAME = "test_result.txt"
ITERATION_DIFF_FILENAME = "diff.txt"
OVERALL_SUMMARY_FILENAME = "overall_summary.txt"


def get_project_structure(project_dir: Path) -> str:
    """Erstellt eine Übersicht der Projektstruktur."""
    structure = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d not in {"__pycache__", "tests", "pathlib2.egg-info"}
        ]
        level = root.replace(str(project_dir), "").count(os.sep)
        indent = " " * 2 * level
        structure.append(f"{indent}{os.path.basename(root)}/")
        subindent = " " * 2 * (level + 1)
        for file in files:
            if file.endswith(".py"):
                structure.append(f"{subindent}{file}")
    return "\n".join(structure)


def backup_project(project_dir: Path, backup_dir: Path) -> None:
    """Erstellt ein Backup des Projekts OHNE Tests."""
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    
    # Kopiere nur Nicht-Test-Dateien
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    for item in project_dir.iterdir():
        if item.name in {'__pycache__', '.git', 'tests', '.pytest_cache', '*.egg-info'}:
            continue
        if item.name.startswith('.'):
            continue
            
        dest = backup_dir / item.name
        
        if item.is_file():
            if item.suffix == '.py' or item.suffix in {'.txt', '.md', '.toml', '.ini', '.cfg'}:
                shutil.copy2(item, dest)
        elif item.is_dir():
            shutil.copytree(
                item,
                dest,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 'tests', '*.egg-info')
            )


def restore_project(backup_dir: Path, project_dir: Path) -> None:
    """Stellt das Projekt aus dem Backup wieder her, OHNE Tests zu löschen."""
    backup_dir = Path(backup_dir).resolve()
    project_dir = Path(project_dir).resolve()

    if not backup_dir.exists():
        raise FileNotFoundError(f"Backup-Verzeichnis nicht gefunden: {backup_dir}")

    # Sichere den Tests-Ordner temporär
    tests_dir = project_dir / "tests"
    temp_tests_dir = None
    
    if tests_dir.exists():
        temp_tests_dir = project_dir.parent / f".temp_tests_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copytree(tests_dir, temp_tests_dir)
    
    try:
        # Lösche nur Nicht-Test-Inhalte
        for item in project_dir.iterdir():
            if item.name == "tests":
                continue
            if item.name.startswith('.'):
                continue
                
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        
        # Kopiere Backup zurück
        for item in backup_dir.iterdir():
            dest = project_dir / item.name
            if item.is_file():
                shutil.copy2(item, dest)
            elif item.is_dir():
                shutil.copytree(item, dest)
        
        # Stelle Tests wieder her
        if temp_tests_dir and temp_tests_dir.exists():
            if tests_dir.exists():
                shutil.rmtree(tests_dir)
            shutil.copytree(temp_tests_dir, tests_dir)
            
    finally:
        # Räume temporäres Tests-Verzeichnis auf
        if temp_tests_dir and temp_tests_dir.exists():
            shutil.rmtree(temp_tests_dir)


def apply_changes(project_dir: Path | str, files: dict[str, str]) -> None:
    """Wendet die Änderungen auf die Dateien an, ignoriert jedoch Dateien im 'tests'-Ordner."""
    project_dir = Path(project_dir).resolve()

    for filename, code in files.items():
        file_rel = Path(filename)

        # Überspringe Test-Dateien
        if any(part == "tests" for part in file_rel.parts):
            print(f" {filename} (Test-Datei, übersprungen)")
            continue

        file_path = (project_dir / file_rel).resolve()
        try:
            file_path.relative_to(project_dir)
        except ValueError:
            print(f" {filename} liegt außerhalb von {project_dir}, übersprungen")
            continue

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(code, encoding="utf-8")
            print(f" {filename} aktualisiert")
        except Exception as e:
            print(f" Fehler beim Schreiben von {filename}: {e}")


def run_pytest():
    """Führt pytest aus und gibt das Ergebnis zurück."""
    try:
        result = subprocess.run(
            ["pytest"],
            capture_output=True,
            text=True,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}



def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_iteration_label(iteration_dir_name: str) -> str:
    """
    Converts "iteration_1" / "iteration_01" / "iteration_001" -> "iteration 1"
    Falls back to the directory name if parsing fails.
    """
    if iteration_dir_name.startswith(ITERATION_PREFIX):
        suffix = iteration_dir_name[len(ITERATION_PREFIX) :].strip()
        try:
            n = int(suffix)
            return f"iteration {n}"
        except ValueError:
            pass
    return iteration_dir_name.replace("_", " ")


def format_summary_line(iteration_dir_name: str, test_success: bool, diff_has_changes: bool) -> str:
    label = parse_iteration_label(iteration_dir_name)
    test_part = "test passed" if test_success else "test failed"
    diff_part = "diff passed" if diff_has_changes else "diff failed"
    return f"{label} {test_part} {diff_part}"


def save_iteration_result_files(
    result_dir: Path,
    test_result: dict[str, object],
    test_status: str,
    diff_status: str,
    diff_text: str,
    note: str | None = None,
) -> None:
    """
    Ensures each iteration folder contains:
    - test_result.txt (test stdout/stderr/returncode + statuses)
    - diff.txt (only diffs, or "(no diff)")
    """
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)

    stdout = str(test_result.get("stdout", ""))
    stderr = str(test_result.get("stderr", ""))
    returncode = str(test_result.get("returncode", ""))

    parts: list[str] = []
    parts.append(f"TEST_STATUS: {test_status}")
    parts.append(f"DIFF_STATUS: {diff_status}")
    parts.append(f"RETURNCODE: {returncode}")
    parts.append(f"TIMESTAMP: {datetime.now().isoformat()}")

    if note:
        parts.append("")
        parts.append(f"NOTE: {note}")

    parts.append("")
    parts.append("=== PYTEST STDOUT ===")
    parts.append(stdout)
    parts.append("")
    parts.append("=== PYTEST STDERR ===")
    parts.append(stderr)
    parts.append("")

    write_text_file(result_dir / ITERATION_RESULT_FILENAME, "\n".join(parts))

    write_text_file(
        result_dir / ITERATION_DIFF_FILENAME,
        diff_text if diff_text else "(no diff)\n",
    )


def should_skip_snapshot_path(relative_path: Path) -> bool:
    """Prüft ob eine Datei im Snapshot übersprungen werden soll."""
    for part in relative_path.parts:
        if "test" in part.lower():
            return True
    return False


def collect_snapshot_files(code_dir: Path) -> dict[str, str]:
    """Sammelt alle Python-Dateien aus dem Snapshot, OHNE Test-Dateien."""
    files: dict[str, str] = {}
    for root, dirs, filenames in os.walk(code_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            file_path = Path(root) / filename
            relative_path = file_path.relative_to(code_dir)
            
            # Überspringe Test-Dateien
            if should_skip_snapshot_path(relative_path):
                continue
                
            try:
                files[str(relative_path)] = file_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"Fehler beim Lesen von {file_path}: {e}")
    return files


def find_iteration_dirs(refactored_root: Path) -> list[Path]:
    iteration_dirs: list[Path] = []
    for root, dirs, _files in os.walk(refactored_root):
        for directory in dirs:
            if directory.startswith(ITERATION_PREFIX):
                iteration_dirs.append(Path(root) / directory)
    iteration_dirs.sort()
    return iteration_dirs


def find_all_refactoring_folders(base_path: Path) -> list[Path]:
    """Findet alle Refactoring-Ordner im base_path."""
    refactoring_folders: list[Path] = []
    
    if not base_path.exists():
        print(f"Warnung: Basisordner {base_path} existiert nicht.")
        return refactoring_folders
    
    for item in base_path.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            # Prüfe ob der Ordner iteration_XX Unterordner enthält
            has_iterations = any(
                d.name.startswith(ITERATION_PREFIX) 
                for d in item.iterdir() 
                if d.is_dir()
            )
            if has_iterations:
                refactoring_folders.append(item)
    
    return sorted(refactoring_folders)


def ensure_within_root(root: Path, target: Path) -> Path:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Ungültiger Ergebnis-Pfad außerhalb von {root_resolved}") from exc
    return target_resolved


def _read_text_best_effort(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""


def _normalize_lines_ignore_whitespace_and_blanklines(text: str) -> list[str]:
    """
    - ignores line breaks by comparing line lists
    - ignores whitespace-only changes by removing all whitespace in each line
    - ignores blank/whitespace-only lines entirely
    """
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
    """
    Returns (has_changes, diff_text).
    - has_changes True if there is at least one meaningful diff (ignoring whitespace/linebreak changes).
    - diff_text contains unified diffs for each changed file.
    """
    diffs: list[str] = []
    has_changes = False

    rel_paths = sorted({str(Path(p)) for p in snapshot_files.keys()})
    for rel in rel_paths:
        rel_path = Path(rel)

        # Überspringe Test-Dateien beim Diff
        if any(part == "tests" for part in rel_path.parts):
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


def process_iteration(
    iteration_dir: Path,
    project_src: Path,
    results_root: Path,
    backup_dir: Path,
) -> tuple[bool, bool, str]:
    code_dir = iteration_dir / "code"
    result_dir = ensure_within_root(results_root, results_root / iteration_dir.name)

    if not code_dir.exists():
        test_result = {"stdout": "", "stderr": "", "returncode": -1, "success": False}
        diff_has_changes = False
        test_status = "FAILURE"
        diff_status = "SUCCESS" if diff_has_changes else "FAILURE"
        save_iteration_result_files(
            result_dir,
            test_result,
            test_status,
            diff_status,
            "",
            note=f"Code-Verzeichnis fehlt: {code_dir}",
        )
        return False, diff_has_changes, format_summary_line(iteration_dir.name, False, diff_has_changes)

    snapshot_files = collect_snapshot_files(code_dir)
    if not snapshot_files:
        test_result = {"stdout": "", "stderr": "", "returncode": -1, "success": False}
        diff_has_changes = False
        test_status = "FAILURE"
        diff_status = "SUCCESS" if diff_has_changes else "FAILURE"
        save_iteration_result_files(
            result_dir,
            test_result,
            test_status,
            diff_status,
            "",
            note=f"Keine Python-Dateien (außer Tests) in {code_dir}",
        )
        return False, diff_has_changes, format_summary_line(iteration_dir.name, False, diff_has_changes)

    # Erstelle Backup OHNE Tests
    backup_project(project_src, backup_dir)

    diff_has_changes = False
    diff_text = ""
    try:
        # Wende nur Nicht-Test-Dateien an
        apply_changes(project_src, snapshot_files)
        
        # Erstelle Diff (ignoriert Tests)
        diff_has_changes, diff_text = build_diff_between_backup_and_refactored(
            backup_dir=backup_dir, project_src=project_src, snapshot_files=snapshot_files
        )
        
        # Führe Tests aus (Tests bleiben unverändert)
        test_result = run_pytest()
    finally:
        # Stelle alles wieder her OHNE Tests zu überschreiben
        restore_project(backup_dir, project_src)

    test_success = bool(test_result.get("success"))
    test_status = "SUCCESS" if test_success else "FAILURE"

    diff_status = "SUCCESS" if diff_has_changes else "FAILURE"

    print(f"  {iteration_dir.name}: TEST={test_status} DIFF={diff_status}")

    save_iteration_result_files(
        result_dir,
        test_result,
        test_status,
        diff_status,
        diff_text,
    )

    return test_success, diff_has_changes, format_summary_line(iteration_dir.name, test_success, diff_has_changes)


def process_refactoring_folder(
    refactoring_folder: Path,
    project_src: Path,
    test_results_base: Path,
) -> dict[str, any]:
    """Verarbeitet einen einzelnen Refactoring-Ordner."""
    print(f"\n{'='*80}")
    print(f"Verarbeite: {refactoring_folder.name}")
    print(f"{'='*80}")
    
    
    results_root = test_results_base / refactoring_folder.name
    results_root.mkdir(parents=True, exist_ok=True)
    backup_dir = ensure_within_root(results_root, results_root / "_backup")

    iteration_dirs = find_iteration_dirs(refactoring_folder)
    
    if not iteration_dirs:
        message = f"Keine iteration_XX Ordner gefunden in {refactoring_folder}\n"
        write_text_file(
            ensure_within_root(results_root, results_root / SUMMARY_FILENAME),
            message,
        )
        print(f"  {message.strip()}")
        return {
            "folder": refactoring_folder.name,
            "iterations": 0,
            "passed": 0,
            "failed": 0,
            "summary_lines": []
        }

    summary_lines: list[str] = []
    passed_count = 0
    failed_count = 0
    
    for iteration_dir in iteration_dirs:
        test_success, _diff_has_changes, line = process_iteration(
            iteration_dir, project_src, results_root, backup_dir
        )
        summary_lines.append(line)
        if test_success:
            passed_count += 1
        else:
            failed_count += 1

    summary_text = "\n".join(summary_lines) + "\n"
    write_text_file(
        ensure_within_root(results_root, results_root / SUMMARY_FILENAME),
        summary_text,
    )

    print(f"\nZusammenfassung für {refactoring_folder.name}:")
    print(f"  Iterationen gesamt: {len(iteration_dirs)}")
    print(f"  Tests bestanden: {passed_count}")
    print(f"  Tests fehlgeschlagen: {failed_count}")
    
    return {
        "folder": refactoring_folder.name,
        "iterations": len(iteration_dirs),
        "passed": passed_count,
        "failed": failed_count,
        "summary_lines": summary_lines
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run pytest for all refactored snapshots in the refactoring folder"
    )
    parser.add_argument(
        "--project-src",
        type=Path,
        default=PROJECT_SRC_PATH,
        help="Pfad zum Projekt-Quellverzeichnis mit Tests",
    )
    parser.add_argument(
        "--refactoring-base",
        type=Path,
        default=REFACTORING_BASE_PATH,
        help="Pfad zum Basisordner mit allen Refactoring-Ergebnissen",
    )
    parser.add_argument(
        "--results-base",
        type=Path,
        default=TEST_RESULTS_BASE,
        help="Pfad zum Basis-Ausgabeordner für test_results",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_src = args.project_src.resolve()
    refactoring_base = args.refactoring_base.resolve()
    results_base = args.results_base.resolve()

    results_base.mkdir(parents=True, exist_ok=True)

    # Finde alle Refactoring-Ordner
    refactoring_folders = find_all_refactoring_folders(refactoring_base)
    
    if not refactoring_folders:
        print(f"Keine Refactoring-Ordner mit Iterationen gefunden in {refactoring_base}")
        return

    print(f"\nGefundene Refactoring-Ordner: {len(refactoring_folders)}")
    for folder in refactoring_folders:
        print(f"  - {folder.name}")

    # Verarbeite jeden Refactoring-Ordner
    all_results: list[dict] = []
    for refactoring_folder in refactoring_folders:
        result = process_refactoring_folder(
            refactoring_folder,
            project_src,
            results_base,
        )
        all_results.append(result)

    # Erstelle Gesamt-Zusammenfassung
    overall_summary_lines: list[str] = []
    overall_summary_lines.append("="*80)
    overall_summary_lines.append("GESAMT-ZUSAMMENFASSUNG")
    overall_summary_lines.append("="*80)
    overall_summary_lines.append("")
    
    total_iterations = 0
    total_passed = 0
    total_failed = 0
    
    for result in all_results:
        overall_summary_lines.append(f"\n{result['folder']}:")
        overall_summary_lines.append(f"  Iterationen: {result['iterations']}")
        overall_summary_lines.append(f"  Bestanden: {result['passed']}")
        overall_summary_lines.append(f"  Fehlgeschlagen: {result['failed']}")
        
        total_iterations += result['iterations']
        total_passed += result['passed']
        total_failed += result['failed']
        
        if result['summary_lines']:
            overall_summary_lines.append("\n  Details:")
            for line in result['summary_lines']:
                overall_summary_lines.append(f"    {line}")
    
    overall_summary_lines.append("\n" + "="*80)
    overall_summary_lines.append("GESAMT:")
    overall_summary_lines.append(f"  Refactoring-Ordner: {len(refactoring_folders)}")
    overall_summary_lines.append(f"  Iterationen gesamt: {total_iterations}")
    overall_summary_lines.append(f"  Tests bestanden: {total_passed}")
    overall_summary_lines.append(f"  Tests fehlgeschlagen: {total_failed}")
    if total_iterations > 0:
        success_rate = (total_passed / total_iterations) * 100
        overall_summary_lines.append(f"  Erfolgsrate: {success_rate:.1f}%")
    overall_summary_lines.append("="*80)
    
    overall_summary = "\n".join(overall_summary_lines) + "\n"
    
    # Schreibe Gesamt-Zusammenfassung
    write_text_file(
        results_base / OVERALL_SUMMARY_FILENAME,
        overall_summary,
    )
    
    print(f"\n\n{overall_summary}")
    print(f"\nErgebnisse gespeichert in: {results_base}")


if __name__ == "__main__":
    main()