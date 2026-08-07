import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pyzipper
import pytest

from core.parser import (
    ACTIVITY_SKIP_DATE_FILTERED,
    ACTIVITY_SKIP_NO_EXPORTABLE_TRACK,
    IncorrectPasswordError,
    InvalidArchiveError,
    UnsupportedExportSchemaError,
    fix_json_content,
    gcj02_to_wgs84_exact,
    parse_huawei_zip,
    process_single_activity,
)


TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
EXT_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
NS = {"t": TCX_NS, "ext": EXT_NS}


def _indoor_activity():
    return {
        "startTime": 1_700_000_000_000,
        "sportType": 101,
        "totalDistance": 1000,
        "totalTime": 100_000,
        "attribute": "HW_EXT_TRACK_DETAIL@istp=p-m;k=10000000;v=500&&",
    }


def _write_huawei_aes_zip(path, password, activities, entry_name=None):
    entry_name = entry_name or (
        "Motion path detail data & description/motion path detail data_1.json"
    )
    with pyzipper.AESZipFile(
        path,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as archive:
        archive.setpassword(password.encode())
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
        archive.writestr(entry_name, json.dumps(activities))


def test_fix_json_content_preserves_structural_newlines():
    source = '{\n  1: 2,\n  "note": "line one\nline two"\n}'

    parsed = json.loads(fix_json_content(source))

    assert parsed == {"1": 2, "note": "line one\nline two"}


def test_gcj_conversion_is_identity_outside_china():
    assert gcj02_to_wgs84_exact(-122.4194, 37.7749) == (-122.4194, 37.7749)


def test_running_cadence_uses_strava_run_cadence_extension_and_exact_km_lap():
    t0 = 1_700_000_000
    lines = []
    for i, (lat, lon) in enumerate(((39.9, 116.4), (39.9001, 116.4001), (39.9002, 116.4002))):
        t = t0 + i * 60
        lines.extend(
            [
                f"istp=lbs;lat={lat};lon={lon};alt=0;t={t}",
                f"istp=s-r;k={t * 1000};v=180",
            ]
        )

    activity = {
        "startTime": t0 * 1000,
        "sportType": 4,
        "totalDistance": 1000,
        "totalTime": 180_000,
        "attribute": (
            'HW_EXT_TRACK_SIMPLIFY@is{"avgStepRate":180}&&'
            "HW_EXT_TRACK_DETAIL@" + "\n".join(lines) + "&&"
        ),
    }

    with tempfile.TemporaryDirectory() as output_dir:
        result = process_single_activity(activity, None, None, output_dir)
        root = ET.parse(Path(output_dir) / result["filename"]).getroot()

    laps = root.findall(".//t:Lap", NS)
    assert len(laps) == 1
    assert float(laps[0].findtext("t:DistanceMeters", namespaces=NS)) == 1000
    assert float(laps[0].findtext("t:TotalTimeSeconds", namespaces=NS)) == 180
    cadence = root.findall(".//ext:RunCadence", NS)
    assert cadence and all(node.text == "90" for node in cadence)
    assert not root.findall(".//t:Cadence", NS)
    assert root.find(".//t:AltitudeMeters", NS).text == "0.0"


def test_indoor_pace_nodes_are_retimed_to_watch_duration_and_distance():
    activity = _indoor_activity()

    with tempfile.TemporaryDirectory() as output_dir:
        result = process_single_activity(activity, None, None, output_dir)
        root = ET.parse(Path(output_dir) / result["filename"]).getroot()

    trackpoints = root.findall(".//t:Trackpoint", NS)
    assert trackpoints[0].findtext("t:DistanceMeters", namespaces=NS) == "0.0"
    assert float(trackpoints[-1].findtext("t:DistanceMeters", namespaces=NS)) == 1000
    assert trackpoints[0].findtext("t:Time", namespaces=NS).endswith("Z")
    assert trackpoints[-1].findtext("t:Time", namespaces=NS) == "2023-11-14T22:15:00Z"
    assert float(root.findtext(".//t:TotalTimeSeconds", namespaces=NS)) == 100


def test_parse_huawei_zip_with_correct_password(tmp_path):
    archive_path = tmp_path / "huawei.zip"
    output_dir = tmp_path / "output"
    _write_huawei_aes_zip(archive_path, "correct", [_indoor_activity()])

    outcome = parse_huawei_zip(str(archive_path), "correct", str(output_dir))

    assert len(outcome.results) == 1
    assert outcome.issues == []
    assert outcome.total_activities == 1
    assert outcome.skipped_activities == 0
    assert (output_dir / outcome.results[0]["filename"]).exists()


def test_parse_huawei_zip_reports_incorrect_password(tmp_path):
    archive_path = tmp_path / "huawei.zip"
    _write_huawei_aes_zip(archive_path, "correct", [_indoor_activity()])

    with pytest.raises(IncorrectPasswordError) as exc_info:
        parse_huawei_zip(str(archive_path), "wrong", str(tmp_path / "output"))

    assert exc_info.value.code == "INCORRECT_PASSWORD"


def test_parse_huawei_zip_reports_corrupted_archive(tmp_path):
    archive_path = tmp_path / "broken.zip"
    archive_path.write_bytes(b"not a zip archive")

    with pytest.raises(InvalidArchiveError) as exc_info:
        parse_huawei_zip(str(archive_path), "secret", str(tmp_path / "output"))

    assert exc_info.value.code == "INVALID_ARCHIVE"


def test_parse_huawei_zip_reports_unsupported_export_schema(tmp_path):
    archive_path = tmp_path / "unsupported.zip"
    _write_huawei_aes_zip(
        archive_path,
        "correct",
        [],
        entry_name="unknown/export.json",
    )

    with pytest.raises(UnsupportedExportSchemaError) as exc_info:
        parse_huawei_zip(str(archive_path), "correct", str(tmp_path / "output"))

    assert exc_info.value.code == "UNSUPPORTED_EXPORT_SCHEMA"


def test_parse_huawei_zip_reports_unsupported_activity_data_shape(tmp_path):
    archive_path = tmp_path / "unsupported-data.zip"
    _write_huawei_aes_zip(archive_path, "correct", {"activities": []})

    outcome = parse_huawei_zip(
        str(archive_path),
        "correct",
        str(tmp_path / "output"),
    )

    assert outcome.results == []
    assert outcome.issues[0].code == "UNSUPPORTED_EXPORT_SCHEMA"


def test_parse_huawei_zip_reports_partial_activity_failure(tmp_path):
    archive_path = tmp_path / "huawei.zip"
    output_dir = tmp_path / "output"
    _write_huawei_aes_zip(
        archive_path,
        "correct",
        [_indoor_activity(), None],
    )

    outcome = parse_huawei_zip(str(archive_path), "correct", str(output_dir))

    assert len(outcome.results) == 1
    assert len(outcome.issues) == 1
    assert outcome.issues[0].code == "ACTIVITY_PARSE_FAILED"
    assert outcome.issues[0].scope == "activity"
    assert outcome.total_activities == 2
    assert outcome.skipped_activities == 0


def test_parse_huawei_zip_counts_date_filtered_activity_as_skipped(tmp_path):
    archive_path = tmp_path / "huawei.zip"
    _write_huawei_aes_zip(archive_path, "correct", [_indoor_activity()])

    outcome = parse_huawei_zip(
        str(archive_path),
        "correct",
        str(tmp_path / "output"),
        start_date="2025-01-01",
    )

    assert outcome.results == []
    assert outcome.issues == []
    assert outcome.total_activities == 1
    assert outcome.skipped_activities == 1
    assert outcome.date_filtered_activities == 1
    assert outcome.no_exportable_activities == 0


def test_process_single_activity_reports_date_filtered_reason(tmp_path):
    result = process_single_activity(
        _indoor_activity(),
        start_ts=2_000_000_000_000,
        end_ts=None,
        output_dir=str(tmp_path),
    )
    assert result == ACTIVITY_SKIP_DATE_FILTERED


def test_process_single_activity_reports_no_exportable_track_reason(tmp_path):
    activity = {
        "startTime": 1_700_000_000_000,
        "sportType": 4,
        "totalDistance": 0,
        "totalTime": 0,
        "attribute": "",
    }
    result = process_single_activity(activity, None, None, str(tmp_path))
    assert result == ACTIVITY_SKIP_NO_EXPORTABLE_TRACK
