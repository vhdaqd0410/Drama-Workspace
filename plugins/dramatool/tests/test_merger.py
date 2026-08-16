from pathlib import Path

from src.core.merger import copy_file, copy_files


def test_copy_file_preserves_source(tmp_path):
    source = tmp_path / "S01E01.mkv"
    target = tmp_path / "S01E02.mkv"
    source.write_text("episode")

    result = copy_file(source, target)

    assert result == target
    assert target.exists()
    assert source.exists()


def test_copy_file_creates_parent_directories_for_cross_folder_moves(tmp_path):
    source = tmp_path / "old" / "S01E01.mkv"
    target = tmp_path / "new" / "S01E02.mkv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("episode")

    results = copy_files([(source, target)])

    assert results == [target]
    assert target.exists()
    assert source.exists()
