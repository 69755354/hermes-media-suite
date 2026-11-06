#!/usr/bin/env python3
"""Build a customer-specific offline package.

A customer package = the standard offline zip + control.json at the package
root.  The agent reads <program>/control.json at startup and starts polling the
control plane, so unpacking + installing is enough to come online; the
activation code still gates every feature.

Usage:
  python3 build_customer_pkg.py --base build_1.2.180/manju-...-offline.zip \
      --customer c_xxxxxxxx --device d_xxx --device-token dev_xxx \
      --customer-token <customer-token> [--label B] --out /tmp/out.zip
"""
import argparse, json, os, sys, zipfile

CONTROL_URL = os.environ.get("MANJU_CONTROL_URL", "https://xingturgzn.cn/ctl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--customer", required=True)
    ap.add_argument("--customer-token", required=True)
    ap.add_argument("--device", required=True)
    ap.add_argument("--device-token", required=True)
    ap.add_argument("--binding-epoch", default="0")
    ap.add_argument("--control-url", default=CONTROL_URL)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    with zipfile.ZipFile(a.base) as z:
        roots = {n.split("/")[0] for n in z.namelist() if "/" in n}
        if len(roots) != 1:
            sys.exit("unexpected package layout: %r" % sorted(roots)[:5])
        root = roots.pop()
        control = {
            "control_url": a.control_url,
            "customer_id": a.customer,
            "customer_token": a.customer_token,
            "device_id": a.device,
            "device_token": a.device_token,
            "binding_epoch": a.binding_epoch,
        }
        payload = json.dumps(control, ensure_ascii=False, indent=1).encode("utf-8")
        with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as out:
            for info in z.infolist():
                data = z.read(info.filename)
                out.writestr(info, data)
            out.writestr(root + "/control.json", payload)
    print("wrote", a.out, os.path.getsize(a.out), "bytes; control.json ->", root)


if __name__ == "__main__":
    main()
