from pathlib import Path
import json
import pytest
from build import APP, LESSON, archive, materials
from q3_validation import create

@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    root=tmp_path_factory.mktemp("validation-bundle")
    output=root/"output";output.mkdir()
    staging=root/"staging";staging.mkdir()
    support=materials(output,staging)
    package=create(output,staging,support,APP,LESSON,archive)
    return output,package

def test_stage_archives_contain_only_their_own_sources(bundle):
    output,packages=bundle
    assert {p.name for p in output.glob("*.zip")}=={"lesson3-starter.zip","lesson3-initial-check.zip","lesson3-expanded-check.zip","lesson3-teacher-reference.zip"}
    for stage,n,pages in [("initial",2,6),("expanded",23,49)]:
        package=packages[stage]
        manifest=json.loads((package/"manifest.json").read_text())
        assert manifest["records"]==n and manifest["physical_pages"]==pages
        inputs=[json.loads(line) for line in (package/"input.jsonl").read_text().splitlines()]
        assert len(inputs)==len({row["id"] for row in inputs})==n
        assert len(list((package/"pdfs").glob("*.pdf")))==n
        assert len(manifest["suites"]["all"])==n

def test_first_and_expanded_checks_are_independent_and_disjoint(bundle):
    _,packages=bundle
    initial=json.loads((packages["initial"]/"manifest.json").read_text())
    expanded=json.loads((packages["expanded"]/"manifest.json").read_text())
    first=set(initial["suites"]["all"]);later=set(expanded["suites"]["all"])
    assert first.isdisjoint(later) and len(first|later)==25
    assert len(expanded["groups"]["edge_cases"]["ids"])==7
    assert expanded["groups"]["edge_cases"]["evaluation_role"]=="posthoc_regression"
    assert set(expanded["groups"])=={"templates","changes","edge_cases"}


def test_archive_bytes_ignore_source_file_mtime(tmp_path):
    import os
    source=tmp_path/"input";source.mkdir()
    file=source/"sample.txt";file.write_text("same content")
    os.utime(file,(1577836800,1577836800));archive(source,tmp_path/"first.zip")
    os.utime(file,(1704067200,1704067200));archive(source,tmp_path/"second.zip")
    assert (tmp_path/"first.zip").read_bytes()==(tmp_path/"second.zip").read_bytes()
