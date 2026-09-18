import unittest

from approved_bom_replay import replay_approved_v10_rows


def row(sku, number, components=(), **columns):
    result = [None] * 133
    result[1], result[2] = number, sku
    result[4] = len(components)
    for index, (part, qty) in enumerate(components):
        result[13 + 4 * index] = part
        result[14 + 4 * index] = qty
    for index, value in columns.items():
        result[int(index)] = value
    return result


def base_rows():
    first_six = [
        ("CON7x50", 10), ("DOW8x30", 4), ("NAIL-1", 5),
        ("FPACK-UNI-P-ACC01-HRD029", 2), ("CAB_SPACER", 4), ("PRIZM-1", 4),
    ]
    hrd = row("UNI-P-ACC01-HRD207D", 1793, first_six)
    analog = row("UNI-P-ACC01-HRD227D", 1795, [
        *first_six[:3], ("FPACK-UNI-P-ACC01-HRD032", 2),
        *first_six[4:], ("LAM186330", 4), ("LAM276308", 1),
    ])
    rows = [hrd, analog]
    number = 50
    for cabinet, color in (("CAB01", "WW"), ("CAB02", "BB"), ("CAB03", "NO")):
        for code, depth, pins in (("SLF021", 564, 6), ("SLF023", 340, 4)):
            shelf = row(f"EUB-C-{cabinet}-{code}", number, [
                (f"EU-SREW-SHELF-FIX-1163x{depth}-{color}", 1),
                (f"HSHELF-{color}-HRD-{pins}", 1),
            ])
            shelf[9], shelf[11] = 1163, depth
            rows.append(shelf)
            number += 1
    return rows


class ApprovedBomReplayTests(unittest.TestCase):
    def test_replay_is_additive_traceable_and_idempotent(self):
        source = base_rows()
        result, changes = replay_approved_v10_rows(source)
        self.assertEqual(len(result), len(source) + 7)
        self.assertEqual(source[0][4], 6)
        self.assertEqual([item["action"] for item in changes].count("ADDED_APPROVED_BOM"), 7)
        self.assertEqual(changes[0]["action"], "APPLIED_APPROVED_HRD207D")
        repeated, repeat_changes = replay_approved_v10_rows(result)
        self.assertEqual(repeated, result)
        self.assertTrue(all(item["action"] == "ALREADY_MATCHING" for item in repeat_changes))

    def test_conflict_is_not_overwritten(self):
        source = base_rows()
        source[0][14] = 9
        with self.assertRaisesRegex(ValueError, "CONFLICTING_APPROVED_BOM"):
            replay_approved_v10_rows(source)

    def test_one_conflict_does_not_discard_other_approved_repairs(self):
        source = base_rows()
        source[0][14] = 9
        repaired, changes = replay_approved_v10_rows(source, allow_conflicts=True)
        self.assertEqual(repaired[0][14], 9)
        self.assertEqual(len(repaired), len(source) + 7)
        self.assertEqual([item["action"] for item in changes].count("CONFLICT_REVIEW"), 1)
        self.assertEqual([item["action"] for item in changes].count("ADDED_APPROVED_BOM"), 7)

    def test_missing_one_analog_does_not_discard_other_approved_repairs(self):
        source = [item for item in base_rows() if item[2] != "EUB-C-CAB02-SLF021"]
        repaired, changes = replay_approved_v10_rows(source, allow_conflicts=True)
        self.assertNotIn("EUB-C-CAB02-SLF020", {item[2] for item in repaired})
        self.assertEqual([item["action"] for item in changes].count("CONFLICT_REVIEW"), 1)
        self.assertEqual([item["action"] for item in changes].count("ADDED_APPROVED_BOM"), 6)


if __name__ == "__main__":
    unittest.main()
