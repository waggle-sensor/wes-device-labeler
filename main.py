import argparse
from os import getenv
import kubernetes
import logging
import time
from pathlib import Path


def get_iio_names(args):
    items = []
    for p in Path(args.root, "sys/bus/iio/devices").glob("*/name"):
        try:
            name = p.read_text().strip().lower()
        except Exception:
            continue
        items.append(name)
    return items


def get_usb_products(args):
    items = []
    for p in Path(args.root, "sys/bus/usb/devices").glob("*/product"):
        try:
            product = p.read_text().strip().lower()
        except Exception:
            continue
        items.append(product)
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="enable debug logging")
    parser.add_argument("--kubeconfig", default=None, help="kubernetes config")
    parser.add_argument("--kubenode", default=getenv("KUBENODE", ""), help="kubernetes node name")
    parser.add_argument("--root", default=Path("/"), type=Path, help="host filesystem root")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S")

    # load incluster service account config
    if args.kubeconfig is None:
        kubernetes.config.load_incluster_config()
    else:
        kubernetes.config.load_kube_config(args.kubeconfig)

    api = kubernetes.client.CoreV1Api()

    # - name: KUBE_NODE_NAME
    #   valueFrom:
    #     fieldRef:
    #       fieldPath: spec.nodeName

    device_list = [
        "bme280",
        "bme680",
        "gps",
        "microphone",
        "raingauge",
    ]

    while True:
        labels = {device: None for device in device_list}
        
        iio_names = get_iio_names(args)
        usb_products = get_usb_products(args)
        
        if "bme280" in iio_names:
            labels["bme280"] = "true"
        
        if "bme680" in iio_names:
            labels["bme680"] = "true"
        
        if Path(args.root, "dev/gps").exists():
            labels["gps"] = "true"

        if "usb audio device" in usb_products:
            labels["microphone"] = "true"

        # NOTE the raingauge uses a generic usb serial connector, so it's hard to tell that it's 
        # specifically the raingauge. we just assume that it's the only one on the rpi
        if "rpi" in args.kubenode and Path(args.root, "dev/ttyUSB0").exists():
            labels["raingauge"] = "true"

        detected = [name for name, label in labels.items() if label is not None]
        logging.info("detected: %s", ", ".join(detected))

        patch = {
            "metadata": {
                "labels": labels
            }
        }

        # update labels host node
        logging.info("updating labels")
        api.patch_node(args.kubenode, patch)

        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
