import argparse
import json
import logging
import subprocess
import time
from os import getenv
from pathlib import Path

import kubernetes


class HardwareDetector:
    def __init__(self, root):
        self.root = root
        self.update()

    def update(self):
        self.iio_names = self.__get_iio_names()
        self.lsusb_output = subprocess.check_output(["lsusb", "-v"]).decode()

    def resource_check_bme280(self):
        return "bme280" in self.iio_names

    def resource_check_bme680(self):
        return "bme680" in self.iio_names

    def resource_check_gps(self):
        return Path(self.root, "dev/gps").exists()

    def resource_check_airquality(self):
        return Path(self.root, "dev/airquality").exists()

    def resource_check_microphone(self):
        return "Microphone" in self.lsusb_output

    def resource_check_rainguage(self):
        # raingauge uses a generic usb serial connector, for now assume it enumerates on USB0
        return Path(self.root, "dev/ttyUSB0").exists()

    def __get_iio_names(self):
        items = []
        for p in Path(self.root, "sys/bus/iio/devices").glob("*/name"):
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
    parser.add_argument(
        "--manifest",
        default=Path("/etc/waggle/node-manifest-v2.json"),
        type=Path,
        help="path to node manifest file",
    )
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

    while True:
        logging.info("scanning for devices")

        # get list of current resources on node and assume not present (will be set below)
        #  this is ensure that if an item (sensor or capability) currently on the node labels disappears, it is removed on the node update below
        node_labels = api.read_node(args.kubenode).metadata.labels
        resources = {i.split(".")[1]: None for i in node_labels if i.split(".")[0] == "resource"}

        # load the node manifest
        with open(args.manifest) as f:
            manifest = json.load(f)

        # get the manifest compute dict for this node
        for compute in manifest["computes"]:
            if compute["serial_no"].lower() in args.kubenode.lower():
                manifest_compute = compute
                break

        # get list of sensors associated to this node
        node_sensors = [s for s in manifest["sensors"] if s["scope"] == manifest_compute["name"]]

        # add the node capabilities
        logging.info("capabilities: %s", manifest_compute["hardware"]["capabilities"])
        for capability in manifest_compute["hardware"]["capabilities"]:
            resources[capability] = "true"

        # check if the hardware exists
        hwDetector = HardwareDetector(root=args.root)
        for sensor in node_sensors:
            sensor_hw = sensor["hardware"]["hardware"]
            logging.info("checking manifest listed sensor: %s", sensor_hw)
            resource_check_func = None
            try:
                resource_check_func = getattr(hwDetector, f"resource_check_{sensor_hw}")
                if resource_check_func():
                    resources[sensor_hw] = "true"
            except:
                logging.exception(
                    "Hardware detection function for [%s] not found, unable to test for hardware.",
                    sensor_hw,
                )

        # log and update the kubernetes node labels
        detected = [name for name, label in resources.items() if label is not None]
        logging.info("applying resources: %s", ", ".join(detected))

        # prefix all resources detect with resource.
        labels = {f"resource.{k}": v for k, v in resources.items()}

        # add optional zone label
        labels["zone"] = manifest_compute["zone"].lower() if manifest_compute["zone"] else None
        logging.info("applying zone: %s", labels["zone"])

        # update labels host node
        if args.dry_run:
            logging.info("dry run - will not update labels")
        else:
            logging.info("updating labels")
            api.patch_node(args.kubenode, {"metadata": {"labels": labels}})

        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
