import argparse
import logging
import time
from os import getenv
from pathlib import Path
import subprocess

import kubernetes


def get_iio_names(args):
    items = []
    for p in Path(args.root, "sys/bus/iio/devices").glob("*/name"):
        try:
            name = p.read_text().strip().lower()
        except Exception:
            continue
        items.append(name)
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="enable debug logging")
    parser.add_argument(
        "--dry-run", action="store_true", help="detect and log labels but don't update"
    )
    parser.add_argument("--kubeconfig", default=None, help="kubernetes config")
    parser.add_argument("--kubenode", default=getenv("KUBENODE", ""), help="kubernetes node name")
    parser.add_argument("--root", default=Path("/"), type=Path, help="host filesystem root")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
    )

    # load incluster service account config
    if args.kubeconfig is None:
        kubernetes.config.load_incluster_config()
    else:
        kubernetes.config.load_kube_config(args.kubeconfig)

    api = kubernetes.client.CoreV1Api()

    device_list = [
        "gpu",
        "bme280",
        "bme680",
        "gps",
        "microphone",
        "raingauge",
    ]

    while True:
        logging.info("scanning for devices")

        resources = {device: None for device in device_list}

        iio_names = get_iio_names(args)

        # tag gpu nodes
        for node in ["nxcore", "nxagent", "sb-core"]:
            if node in args.kubenode:
                resources["gpu"] = "true"

        if "bme280" in iio_names:
            resources["bme280"] = "true"

        if "bme680" in iio_names:
            resources["bme680"] = "true"

        if Path(args.root, "dev/gps").exists():
            resources["gps"] = "true"

        lsusb_output = subprocess.check_output(["lsusb", "-v"]).decode()

        if "Microphone" in lsusb_output:
            resources["microphone"] = "true"

        # NOTE the raingauge uses a generic usb serial connector, so it's hard to tell that it's
        # specifically the raingauge. we just assume that it's the only one on the rpi
        if "rpi" in args.kubenode and Path(args.root, "dev/ttyUSB0").exists():
            resources["raingauge"] = "true"

        detected = [name for name, label in resources.items() if label is not None]
        logging.info("detected: %s", ", ".join(detected))

        # prefix all resources detect with resource.
        labels = {f"resource.{k}": v for k, v in resources.items()}

        patch = {"metadata": {"labels": labels}}

        # update labels host node
        if args.dry_run:
            logging.info("dry run - will not update labels")
        else:
            logging.info("updating labels")
            api.patch_node(args.kubenode, patch)

        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
