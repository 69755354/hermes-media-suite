#!/usr/bin/env python3
"""Guard the two cover-step invariants that have already caused two outages.

A future build/patch that silently drops either invariant must fail here
instead of failing on the customer machine at publish time:

  1. fill() must wait for upload/transcode BEFORE touching the cover panel.
  2. _choose_cover() must skip the whole cover panel + cover check when the
     plan requested no cover (no covers, no upload opt-in, no AI opt-in).

Usage: check_publish_invariants.py <publish_exec.py> [...]
Exit 0 = all invariants hold, 1 = regression found.
"""
import sys
from pathlib import Path


def _publish_fill(src):
    """The publish flow's fill(); another class has a different fill()."""
    start = 0
    while True:
        i = src.find("def fill(self, plan):", start)
        if i < 0:
            return ""
        body = src[i:i + 9000]
        if "_upload_video(media)" in body:
            return body
        start = i + 1


def check(path: Path):
    src = path.read_text(encoding="utf-8")
    problems = []

    fill_body = _publish_fill(src)
    if not fill_body:
        problems.append("publish fill() not found")
    else:
        i_choose = fill_body.find("self._choose_cover(")
        i_wait = fill_body.find("self._wait_transcode()")
        if i_choose < 0 or i_wait < 0:
            problems.append("fill() lost _choose_cover/_wait_transcode")
        elif i_wait > i_choose:
            problems.append("REGRESSION: fill() calls _choose_cover before _wait_transcode")

    choose = src.find("def _choose_cover(self, covers")
    if choose < 0:
        problems.append("_choose_cover() not found")
    else:
        head = src[choose:choose + 2500]
        i_skip = head.find('reason="no_cover_requested"')
        i_open = head.find("self._open_cover_panel()")
        if i_skip < 0:
            problems.append("REGRESSION: _choose_cover() no longer skips when no cover is requested")
        elif i_open >= 0 and i_open < i_skip:
            problems.append("REGRESSION: no-cover skip happens after opening the cover panel")

    # 3. Star-task matching must survive the category word -> full task title
    #    gap.  The bot sends "APP种草" while the picker card reads
    #    "火龙漫剧星广-260916-APP种草-1-优矩互动"; exact equality can never
    #    match.  A build that drops the containment fallback dies at
    #    XINGTU_TASK_NOT_ATTACHED after the video is already uploaded.
    i_match = src.find("def matching_rows():")
    if i_match < 0:
        problems.append("xingtu matching_rows() not found")
    else:
        body = src[i_match:i_match + 4000]
        if "return exact or contained" not in body:
            problems.append("REGRESSION: xingtu matching lost the containment "
                            "fallback (exact equality only)")
        if "def _card_names" not in src:
            problems.append("REGRESSION: xingtu matching lost the observed-card "
                            "diagnostics")
        if 'search.fill("")' not in body:
            problems.append("REGRESSION: xingtu matching lost the clear-search "
                            "retry")
    # 4. The picker-card query must be scoped to the star-task portal.  A
    #    document-wide [class*=card-container] also matches the page layout
    #    wrapper, which turns the whole form into one "card" and makes every
    #    task match fail after the video is already uploaded.
    i_rows = src.find("def _xingtu_card_rows(page):")
    if i_rows < 0:
        problems.append("_xingtu_card_rows() not found")
    else:
        rows_body = src[i_rows:i_rows + 3500]
        if ".semi-portal" not in rows_body:
            problems.append("REGRESSION: _xingtu_card_rows lost the portal scope")
        if "data-xt-idx" not in rows_body:
            problems.append("REGRESSION: _xingtu_card_rows lost the per-card "
                            "click handle")
    # 5. Star-task card clicks must be trusted mouse clicks.  A synthetic
    #    dispatch_event("click") never runs a label's default activation, so
    #    semi-radio stays unchecked and publish aborts with "star task card
    #    did not become selected" after the video is already uploaded.
    sib = path.with_name("xingtu_tasks.py")
    if not sib.exists():
        problems.append("xingtu_tasks.py not found next to publish_exec.py")
    else:
        xt = sib.read_text(encoding="utf-8")
        i_click = xt.find("def click_picker_element")
        if i_click < 0:
            problems.append("click_picker_element() not found")
        else:
            body = xt[i_click:i_click + 1400]
            i_real = body.find("item.click(timeout=2000)")
            i_dispatch = body.find('item.dispatch_event("click"')
            if i_real < 0:
                problems.append("REGRESSION: click_picker_element lost the trusted "
                                "mouse click (label/radio default never fires)")
            elif i_dispatch >= 0 and i_dispatch < i_real:
                problems.append("REGRESSION: click_picker_element dispatches a "
                                "synthetic click before the trusted one")
    # 6. The picker re-renders when its search filter applies and reassigns
    #    data-xt-idx.  The row index must be re-read right before clicking,
    #    with one retry, or the radio click lands on another card / nothing.
    if "fresh_rows = matching_rows()" not in src:
        problems.append("REGRESSION: star-task selection no longer re-resolves "
                        "the card index before clicking")
    if "retry_rows = matching_rows()" not in src:
        problems.append("REGRESSION: star-task selection lost its index refresh "
                        "retry")
    # 7. A card-container click does not toggle the wrapped semi-radio on the
    #    Douyin picker; only the label does.  Fill mode used to short-circuit
    #    after the card click and report success without ever reading the
    #    radio, so the task was never attached and the form readback failed.
    i_select = src.find("def _xingtu_select_fill_row(")
    if i_select < 0:
        problems.append("_xingtu_select_fill_row() not found")
    else:
        body = src[i_select:i_select + 2600]
        if 'label.semi-radio' not in body:
            problems.append("REGRESSION: star-task selection no longer clicks "
                            "the radio label (card click leaves it unchecked)")
        if "for target in (radio_label, radio, card):" not in body:
            problems.append("REGRESSION: star-task selection lost the "
                            "label/radio/card click order")
        if "if not wait_for_selection:" in body:
            problems.append("REGRESSION: fill-mode selection returns before "
                            "verifying the radio is checked")
    # 8. Mount evidence lives in the publish form, not the picker.  The
    #    attached task renders as a card-container block whose 更换/删除 live
    #    in a wrapper above it, so a contract that demands direct-sibling
    #    controls finds zero blocks and fails every attach.
    i_mount = src.find("def _xingtu_mount_contract(")
    if i_mount < 0:
        problems.append("_xingtu_mount_contract() not found")
    else:
        body = src[i_mount:i_mount + 4200]
        if "form_card" not in body:
            problems.append("REGRESSION: mount contract lost the form-card "
                            "readback path")
        if "请选择星图任务" not in body:
            problems.append("REGRESSION: mount contract no longer checks the "
                            "unselected-task placeholder")
        if "depth < 3" not in body:
            problems.append("REGRESSION: mount contract no longer looks above "
                            "the card for its 更换/删除 controls")
    return problems


def main(argv):
    targets = [Path(a) for a in argv[1:]]
    if not targets:
        print("usage: check_publish_invariants.py <publish_exec.py>")
        return 2
    bad = 0
    for target in targets:
        problems = check(target)
        if problems:
            bad += 1
            print("FAIL", target)
            for item in problems:
                print("  -", item)
        else:
            print("PASS", target)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
