from bom_archive_blockers import assess_line


def line(ordered, delivered, invoiced):
    return {"id": 101, "order_id": [1, "SO001"], "product_id": [10, "Main product"], "product_uom_qty": ordered, "qty_delivered": delivered, "qty_invoiced": invoiced}


def test_open_unfulfilled_line_blocks():
    row = assess_line(line(4, 0, 0), {"name": "SO001", "state": "sale"})
    assert row.blocks_archive is True
    assert row.zero_residual_line is False


def test_zero_residual_line_is_marked_but_not_blocking():
    row = assess_line(line(0, 0, 0), {"name": "SO001", "state": "done"})
    assert row.blocks_archive is False
    assert row.zero_residual_line is True


def test_fully_completed_line_does_not_block():
    row = assess_line(line(3, 3, 3), {"name": "SO001", "state": "done"})
    assert row.blocks_archive is False
    assert row.zero_residual_line is False
