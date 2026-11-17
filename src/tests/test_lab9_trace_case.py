"""Regression test for docs/trace_case.md: FM-05 (pre_deducted) on C-014@11."""
import pytest

pytestmark = pytest.mark.student
CLAIM, SEED = "C-014", 11


def run(shape):
    from lab9.trace_case import investigate

    case = investigate(shape, CLAIM, SEED)
    return case["trial"], case["label"]


def test_fixed_refunds_the_labelled_amount():
    trial, label = run("fixed")
    assert trial["snapshot"]["refund_vnd"] == label["refund_vnd"] == 120000
    assert not [e for e in trial["events"] if e["kind"] == "proposal"]


def test_pre_deducted_proposal_is_caught_on_the_ledger():
    trial, label = run("seeded_regression")
    proposals = [e["payload"]["amount_vnd"] for e in trial["events"] if e["kind"] == "proposal"]
    assert proposals == [120000]                       # first wrong step: agent deducts the 30.000đ itself
    assert trial["snapshot"]["refund_vnd"] == 90000    # host deducts again
    assert trial["snapshot"]["refund_vnd"] != label["refund_vnd"]
