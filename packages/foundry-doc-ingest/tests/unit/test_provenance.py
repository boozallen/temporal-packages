# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
import os
import re

from foundry_doc_ingest.provenance import get_provenance, update_provenance


def test_write_and_query_record(activity_environment, tmp_db):
    activity_environment.run(update_provenance, "wf-1", "doc.pdf", "validate", "success", db_path=tmp_db)
    records = get_provenance("wf-1", db_path=tmp_db)
    assert len(records) == 1
    assert records[0].workflow_id == "wf-1"
    assert records[0].file_reference == "doc.pdf"
    assert records[0].step_name == "validate"
    assert records[0].outcome == "success"


def test_auto_create_db(activity_environment, tmp_dir):
    db_path = os.path.join(tmp_dir, "new_db.db")
    assert not os.path.exists(db_path)
    activity_environment.run(update_provenance, "wf-1", "file.txt", "store", "success", db_path=db_path)
    assert os.path.exists(db_path)


def test_append_to_existing(activity_environment, tmp_db):
    activity_environment.run(update_provenance, "wf-1", "a.txt", "step1", "success", db_path=tmp_db)
    activity_environment.run(update_provenance, "wf-1", "a.txt", "step2", "failure", db_path=tmp_db)
    records = get_provenance("wf-1", db_path=tmp_db)
    assert len(records) == 2
    assert records[0].step_name == "step1"
    assert records[1].step_name == "step2"


def test_query_by_workflow_id(activity_environment, tmp_db):
    activity_environment.run(update_provenance, "wf-1", "a.txt", "validate", "success", db_path=tmp_db)
    activity_environment.run(update_provenance, "wf-2", "b.txt", "validate", "success", db_path=tmp_db)
    records = get_provenance("wf-1", db_path=tmp_db)
    assert len(records) == 1
    assert records[0].workflow_id == "wf-1"


def test_query_no_results(activity_environment, tmp_db):
    # Ensure DB exists with table
    activity_environment.run(update_provenance, "wf-1", "a.txt", "step", "ok", db_path=tmp_db)
    records = get_provenance("nonexistent", db_path=tmp_db)
    assert records == []


def test_timestamp_format(activity_environment, tmp_db):
    activity_environment.run(update_provenance, "wf-1", "doc.pdf", "validate", "success", db_path=tmp_db)
    records = get_provenance("wf-1", db_path=tmp_db)
    # ISO 8601 UTC: 2026-04-21T14:30:00Z
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", records[0].timestamp)
