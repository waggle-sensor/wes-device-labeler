import argparse
import json
import logging
import subprocess
import time
from os import getenv
from pathlib import Path
import re

import kubernetes


class HardwareDetector:
    def __init__(self, root):
        self.root = root
        self.update()

    def update(self):
        self.iio_names = self.__get_iio_names()
        self.lsusb_output = subprocess.check_output(["lsusb", "-v"]).decode()

    # NOTE(sean) Joe used getattr in the main function to dyamically find the various
    # resource_check_xyz functions below.

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

    def resource_check_raingauge(self):
        # raingauge uses a generic usb serial connector, for now assume it enumerates on USB0
        return Path(self.root, "dev/ttyUSB0").exists()

    def resource_check_lorawan(self):
        # TODO Decide on an actual hardware check. For now, this basically applies the label
        # if it's in the manifest without any further checks.
        return True

    def __get_iio_names(self):
        items = []
        for p in Path(self.root, "sys/bus/iio/devices").glob("*/name"):
            try:
                name = p.read_text().strip().lower()
            except Exception:
                continue
            items.append(name)
        return items


# This was added in Python 3.9, but I'm just adding a stub here.
def removeprefix(s, p):
    if s.startswith(p):
        return s[len(p) :]
    return s


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="enable debug logging")
    parser.add_argument(
        "--dry-run", action="store_true", help="detect and log labels but don't update"
    )
    parser.add_argument("--kubeconfig", default=None, help="kubernetes config")
    parser.add_argument(
        "--kubenode", default=getenv("KUBENODE", ""), help="kubernetes node name"
    )
    parser.add_argument(
        "--root", default=Path("/"), type=Path, help="host filesystem root"
    )
    parser.add_argument(
        "--manifest",
        default=Path("/etc/waggle/node-manifest-v2.json"),
        type=Path,
        help="path to node manifest file",
    )
    parser.add_argument(
        "--oneshot", action="store_true", help="enable to only test once"
    )
    parser.add_argument(
        "--delay", default=60, type=int, help="time (s) between detection loops"
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

    if args.oneshot:
        args.delay = 0

    run_once = False
    while not args.oneshot or (args.oneshot and not run_once):
        logging.info("sleep %ds...", args.delay)
        time.sleep(args.delay)
        logging.info("scanning for devices")
        run_once = True

        # get list of current resources on node and assume not present (will be set below)
        #  this is ensure that if an item (sensor or capability) currently on the node labels disappears, it is removed on the node update below
        try:
            node_labels = api.read_node(args.kubenode).metadata.labels
        except:
            # log and try again later
            logging.exception(
                "Exception attempting to read kubernetes node [%s] info, try again later.",
                args.kubenode,
            )
            continue
        resources = {
            i.split(".")[1]: None for i in node_labels if i.split(".")[0] == "resource"
        }

        # load the node manifest
        with open(args.manifest) as f:
            manifest = json.load(f)

        # get the manifest compute dict for this node
        manifest_compute = None
        for compute in manifest["computes"]:
            # strip the kube node to the 12 character mac address (0000e45f012a1f42.ws-rpi -> e45f012a1f42)
            if (
                compute["serial_no"].lower()
                == args.kubenode.lower().split(".")[0][-12:]
            ):
                manifest_compute = compute
                break

        if not manifest_compute:
            raise Exception(f"Unable to find compute {args.kubenode} in manifest")

        # get list of sensors associated to this node
        node_sensors = [
            s for s in manifest["sensors"] if s["scope"] == manifest_compute["name"]
        ]

        # add the node capabilities
        logging.info("capabilities: %s", manifest_compute["hardware"]["capabilities"])
        for capability in manifest_compute["hardware"]["capabilities"]:
            resources[capability] = "true"

        # check if the hardware exists
        hwDetector = HardwareDetector(root=args.root)
        for sensor in node_sensors:
            sensor_hw = sensor["hardware"]["hardware"]
            logging.info("checking manifest listed sensor: %s", sensor_hw)
            resource_check_func = getattr(
                hwDetector, f"resource_check_{sensor_hw}", None
            )

            if resource_check_func is None:
                logging.error(
                    "Hardware detection function for [%s] not found, unable to test for hardware.",
                    sensor_hw,
                )
                continue

            if resource_check_func():
                resources[sensor_hw] = "true"

        # NOTE(sean) For the upcoming udev based device names, I'm am just check what's on node and not
        # cross checking the manifest. I think this is a bit simpler and we will likely have the right
        # config tracked by the time a udev rule is actually set.
        for path in Path(args.root, "dev").glob("waggle-*"):
            name = removeprefix(path.name, "waggle-")
            if not re.fullmatch(r"[a-z0-9-]+", name):
                logging.warning("invalid device name %s - ignoring", name)
                continue
            resources[name] = "true"

        # log and update the kubernetes node labels
        detected = [name for name, label in resources.items() if label is not None]
        logging.info("applying resources: %s", ", ".join(sorted(detected)))

        # prefix all resources detect with resource.
        labels = {f"resource.{k}": v for k, v in resources.items()}

        # add optional zone label
        labels["zone"] = (
            manifest_compute["zone"].lower() if manifest_compute["zone"] else None
        )
        logging.info("applying zone: %s", labels["zone"])

        # update labels host node
        if args.dry_run:
            logging.info("dry run - will not update labels")
        else:
            logging.info("updating labels")
            try:
                api.patch_node(args.kubenode, {"metadata": {"labels": labels}})
            except:
                # log and try again later
                logging.exception(
                    "Exception attempting to apply labels to kubernetes node [%s], try again later.",
                    args.kubenode,
                )
                continue


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except KeyboardInterrupt:
        pass
