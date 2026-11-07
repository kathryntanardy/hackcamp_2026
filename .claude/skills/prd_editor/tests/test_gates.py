import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_headings as ch  # noqa: E402

PRD = """# Demo PRD

Intro line.

## Scope

We build feature Foo and feature Bar.

## Data model

Table repos(id, name).

```md
## not a heading (inside fence)
```

## Demo script

Show Foo, then Bar.
"""


def run_check(before_text, after_text, **kw):
    before = ch.snapshot(before_text)
    return ch.check(before, after_text, kw.get("edits", []),
                    kw.get("structure_change", False), kw.get("stale", []))


def test_fenced_heading_ignored():
    assert ch.snapshot(PRD)["headings"] == ["(preamble)", "Scope", "Data model", "Demo script"]


def test_clean_declared_edit_passes():
    after = PRD.replace("Table repos(id, name).", "Table repos(id, name, stars).")
    changed, failures = run_check(PRD, after, edits=["Data model"])
    assert changed == ["Data model"]
    assert failures == []


# Gate 1: reword an unrelated section -> flagged
def test_gate1_undeclared_change_fails():
    after = PRD.replace("Table repos(id, name).", "Table repos(id, name, stars).")
    after = after.replace("Show Foo, then Bar.", "Show Foo and then Bar.")
    _, failures = run_check(PRD, after, edits=["Data model"])
    assert any("Undeclared" in f and "Demo script" in f for f in failures)


def test_gate1_unknown_edit_name_fails():
    _, failures = run_check(PRD, PRD, edits=["Datamodel"])
    assert any("not found" in f for f in failures)


# Gate 2: rename a heading -> structure fails
def test_gate2_rename_heading_fails():
    after = PRD.replace("## Data model", "## Schema")
    _, failures = run_check(PRD, after, edits=["Data model"])
    assert any("Heading structure changed" in f for f in failures)


def test_gate2_allowed_when_declared():
    after = PRD + "## Risks\n\nNone.\n"
    _, failures = run_check(PRD, after, structure_change=True)
    assert failures == []


# Gate 3: drop Foo but leave it in Demo script -> caught
def test_gate3_stale_term_fails():
    after = PRD.replace("feature Foo and feature Bar", "feature Bar")
    _, failures = run_check(PRD, after, edits=["Scope"], stale=["Foo"])
    assert any("Stale term 'Foo'" in f for f in failures)


def test_gate3_clean_removal_passes():
    after = PRD.replace("feature Foo and feature Bar", "feature Bar")
    after = after.replace("Show Foo, then Bar.", "Show Bar.")
    _, failures = run_check(PRD, after, edits=["Scope", "Demo script"], stale=["Foo"])
    assert failures == []


def test_cli_exit_codes(tmp_path):
    prd = tmp_path / "PRD.md"
    snap = tmp_path / "snap.json"
    prd.write_text(PRD)
    script = str(SCRIPTS / "check_headings.py")
    subprocess.run([sys.executable, script, "snapshot", str(prd), str(snap)], check=True)
    assert json.loads(snap.read_text())["headings"][1] == "Scope"
    ok = subprocess.run([sys.executable, script, "check", str(snap), str(prd)])
    assert ok.returncode == 0
    prd.write_text(PRD.replace("Intro line.", "Changed."))
    bad = subprocess.run([sys.executable, script, "check", str(snap), str(prd)])
    assert bad.returncode == 1


# Gate 4: diff is empty right after a PRD commit; non-empty after code changes
def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _diff(repo):
    return subprocess.run(["bash", str(SCRIPTS / "get_diff.sh")], cwd=repo,
                          capture_output=True, text=True)


def test_gate4_get_diff(tmp_path):
    repo = tmp_path
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "app.py").write_text("x = 1\n")
    (repo / "PRD.md").write_text(PRD)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")

    r = _diff(repo)
    assert r.returncode == 0 and r.stdout == ""  # nothing to sync

    (repo / "PRD.md").write_text(PRD + "edit\n")  # PRD edits alone don't count
    assert _diff(repo).stdout == ""

    (repo / "app.py").write_text("x = 2\n")       # uncommitted change
    (repo / "new.py").write_text("y = 1\n")       # untracked file
    out = _diff(repo).stdout
    assert "+x = 2" in out
    assert "untracked: new.py" in out


def test_gate4_no_prd_commit_errors(tmp_path):
    _git(tmp_path, "init", "-q")
    r = _diff(tmp_path)
    assert r.returncode == 2
