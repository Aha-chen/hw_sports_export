import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from core.parser import fix_json_content, gcj02_to_wgs84_exact, process_single_activity


TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
EXT_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
NS = {"t": TCX_NS, "ext": EXT_NS}


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
        lines.extend([
            f"istp=lbs;lat={lat};lon={lon};alt=0;t={t}",
            f"istp=s-r;k={t * 1000};v=180",
        ])

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
    t0 = 1_700_000_000
    activity = {
        "startTime": t0 * 1000,
        "sportType": 101,
        "totalDistance": 1000,
        "totalTime": 100_000,
        "attribute": (
            'HW_EXT_TRACK_DETAIL@istp=p-m;k=10000000;v=500&&'
        ),
    }

    with tempfile.TemporaryDirectory() as output_dir:
        result = process_single_activity(activity, None, None, output_dir)
        root = ET.parse(Path(output_dir) / result["filename"]).getroot()

    trackpoints = root.findall(".//t:Trackpoint", NS)
    assert trackpoints[0].findtext("t:DistanceMeters", namespaces=NS) == "0.0"
    assert float(trackpoints[-1].findtext("t:DistanceMeters", namespaces=NS)) == 1000
    assert trackpoints[0].findtext("t:Time", namespaces=NS).endswith("Z")
    assert trackpoints[-1].findtext("t:Time", namespaces=NS) == "2023-11-14T22:15:00Z"
    assert float(root.findtext(".//t:TotalTimeSeconds", namespaces=NS)) == 100
