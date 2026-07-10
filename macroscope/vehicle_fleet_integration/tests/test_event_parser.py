import datetime
import json
import os

from django.test import SimpleTestCase

from vehicle_fleet_integration.event_parser import extract_plate_event, parse_event_line

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'plate_event.json')


def load_fixture():
    with open(FIXTURE_PATH, encoding='utf-8') as fh:
        return json.load(fh)


class ParseEventLineTests(SimpleTestCase):
    def test_parses_valid_json_line(self):
        data = parse_event_line(json.dumps(load_fixture()))
        self.assertIsNotNone(data)
        self.assertEqual(data['EventId'], 'c9d6d086-c965-4cf8-aef6-85b3894e3a4a')

    def test_ignores_keepalive(self):
        keepalive = json.dumps({'InitiatorName': 'System'})
        self.assertIsNone(parse_event_line(keepalive))

    def test_ignores_malformed_line(self):
        self.assertIsNone(parse_event_line('not-json'))


class ExtractPlateEventTests(SimpleTestCase):
    def test_extracts_fields_from_fixture(self):
        parsed = extract_plate_event(load_fixture())
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.event_id, 'c9d6d086-c965-4cf8-aef6-85b3894e3a4a')
        self.assertEqual(parsed.numberplate, 'A123BC77')
        self.assertEqual(parsed.direction, 'Въезд')
        self.assertAlmostEqual(parsed.reliability, 0.9999972581863403)
        self.assertEqual(parsed.passed_at.year, 2024)
        self.assertEqual(parsed.recognized_brand, 'Toyota')

    def test_returns_none_for_other_event_types(self):
        data = dict(load_fixture(), EventDescription='Другое событие')
        self.assertIsNone(extract_plate_event(data))

    def test_returns_none_when_required_field_missing(self):
        data = dict(load_fixture())
        del data['Numberplate']
        del data['plateText']
        self.assertIsNone(extract_plate_event(data))

    def test_returns_none_for_unparsable_timestamp(self):
        data = dict(load_fixture())
        data['ZonedTimestamp'] = 'не дата'
        del data['Timestamp']
        self.assertIsNone(extract_plate_event(data))

    def test_bare_timestamp_without_offset_uses_terminal_timezone(self):
        data = dict(load_fixture())
        del data['ZonedTimestamp']  # остаётся только Timestamp без offset: "26.03.2024 11:23:22"
        parsed = extract_plate_event(data)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.passed_at.utcoffset(), datetime.timedelta(hours=3))
        self.assertEqual(parsed.passed_at.hour, 11)
