"""核对随档资料可以读取，以及原始记录引用完整。"""

from pathlib import Path
import tempfile
import unittest

from inspect_records import load_records


class RecordsTest(unittest.TestCase):
    def setUp(self):
        self.data = load_records(Path(__file__).parent / "data" / "records.json")

    def test_record_references(self):
        for source, field, target in [('playback', 'clip', 'cuts'), ('resume', 'clip', 'cuts'), ('mapping', 'a', 'cuts'), ('mapping', 'b', 'cuts')]:
            group, _, key = target.partition(".")
            keys = {row[key or "id"] for row in self.data[group]}
            for row in self.data[source]:
                refs = row.get(field)
                if refs is None:
                    continue
                refs = refs if isinstance(refs, list) else [refs]
                with self.subTest(kind=source, record=row["id"], field=field):
                    self.assertLessEqual(set(refs), keys)

    def test_duplicate_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"组":[{"id":"1"},{"id":"1"}]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "编号重复"):
                load_records(path)

    def test_source_packet(self):
        for item in self.data["cuts"]:
            for track in ("text", "screen"):
                self.assertTrue(all(0 <= line[0] < line[1] for line in item[track]))
        self.assertTrue(all(0 <= start < end for item in self.data["playback"] for start, end in item["played"]))
        self.assertTrue({r["kind"] for r in self.data["changes"]} >= {"删除播放", "修订场记"})
        self.assertEqual(len({r["version"] for r in self.data["cuts"]}), 2)


if __name__ == "__main__":
    unittest.main()
