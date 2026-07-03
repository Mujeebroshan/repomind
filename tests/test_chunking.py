from pathlib import Path

from codechat.chunking import chunk_file, chunk_repo, discover_files


def make_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".git").mkdir()

    (tmp_path / "src" / "main.py").write_text("\n".join(f"line {i}" for i in range(1, 151)))
    (tmp_path / "src" / "empty.py").write_text("")
    (tmp_path / "node_modules" / "ignored.py").write_text("should not be picked up")
    (tmp_path / "README.md").write_text("# hello\nworld\n")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")
    return tmp_path


def test_discover_files_skips_excluded_dirs_and_extensions(tmp_path):
    repo = make_repo(tmp_path)
    files = discover_files(repo)
    rels = {str(f.relative_to(repo)) for f in files}

    assert "src/main.py" in rels
    assert "README.md" in rels
    assert not any("node_modules" in r for r in rels)
    assert not any(".git" in r for r in rels)
    assert "image.png" not in rels
    # empty files are skipped
    assert "src/empty.py" not in rels


def test_chunk_file_produces_overlapping_windows(tmp_path):
    repo = make_repo(tmp_path)
    chunks = chunk_file(repo, repo / "src" / "main.py")

    assert len(chunks) > 1
    # first chunk starts at line 1
    assert chunks[0].start_line == 1
    # every chunk has well-formed line ranges
    for c in chunks:
        assert c.start_line <= c.end_line
        assert c.file_path == "src/main.py"
    # last chunk reaches the end of the file (150 lines)
    assert chunks[-1].end_line == 150
    # consecutive chunks overlap rather than skipping lines
    assert chunks[1].start_line < chunks[0].end_line


def test_chunk_repo_aggregates_across_files(tmp_path):
    repo = make_repo(tmp_path)
    files, chunks = chunk_repo(repo)
    assert len(files) >= 2
    assert any(c.file_path == "README.md" for c in chunks)
