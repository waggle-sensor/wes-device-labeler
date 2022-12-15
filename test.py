import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from main import main

NODE_NONE = "0000000000000000.ws-none"
NODE_NXCORE = "0000000000000001.ws-nxcore"
NODE_NXAGENT = "0000000000000002.ws-nxagent"
NODE_RPI_SHIELD = "0000000000000003.ws-rpi"
NODE_RPI_ENCLOSURE = "0000000000000004.ws-rpi"
NODE_BLADECORE = "0000000000000005.sb-core"

NODE_MANIFEST_WSN = "test_files/node-manifest-v2-wsn.json"
NODE_MANIFEST_BLADE = "test_files/node-manifest-v2-blade.json"
NODE_MANIFEST_HW_DETECT_FAIL = "test_files/node-manifest-v2-lidar-fail.json"


@patch("kubernetes.config.load_incluster_config", return_value=Mock())
@patch("kubernetes.config.load_kube_config", return_value=Mock())
# this 'bogus' resource should not show up in any results (i.e. be removed)
@patch(
    "kubernetes.client.CoreV1Api",
    return_value=Mock(
        read_node=Mock(return_value=Mock(metadata=Mock(labels={"resource.bogus=True"})))
    ),
)
@patch("subprocess.check_output", return_value=Mock(decode=Mock(return_value="Microphone")))
class TestService(unittest.TestCase):
    def setUp(self):
        self.root_tmpdr = tempfile.TemporaryDirectory()
        self.root = self.root_tmpdr.name
        Path.mkdir(Path(self.root, "dev"), parents=True)
        Path.mkdir(Path(self.root, "sys/bus/iio/devices/iio1"), parents=True)
        Path.mkdir(Path(self.root, "sys/bus/iio/devices/iio2"), parents=True)

    def tearDown(self):
        self.root_tmpdr.cleanup()

    def testNXCore(self, mock_k_lic, mock_k_lkc, mock_k_core, mock_subprocess):
        with patch("argparse.ArgumentParser.parse_args") as mock:

            # make the fake device and system files
            Path(self.root, "dev/gps").touch()
            Path(self.root, "dev/airquality").touch()
            with open(Path(self.root, "sys/bus/iio/devices/iio1/name"), "w") as f:
                f.write("bme280")

            with self.assertLogs() as logs:
                mock.return_value = argparse.Namespace(
                    debug=None,
                    dry_run=True,
                    kubeconfig=None,
                    kubenode=NODE_NXCORE,
                    root=self.root,
                    manifest=NODE_MANIFEST_WSN,
                    oneshot=True,
                )
                main()
        self.assertIn(
            "INFO:root:applying resources: airquality, arm64, bme280, cuda102, gps, gpu",
            logs.output,
        )
        self.assertIn("INFO:root:applying zone: core", logs.output)

    def testNXAgent(self, mock_k_lic, mock_k_lkc, mock_k_core, mock_subprocess):
        with patch("argparse.ArgumentParser.parse_args") as mock:

            # no device/system files

            with self.assertLogs() as logs:
                mock.return_value = argparse.Namespace(
                    debug=None,
                    dry_run=True,
                    kubeconfig=None,
                    kubenode=NODE_NXAGENT,
                    root=self.root,
                    manifest=NODE_MANIFEST_WSN,
                    oneshot=True,
                )
                main()
        self.assertIn("INFO:root:applying resources: arm64, cuda102, gpu, poe", logs.output)
        # Test for a compute unit withOUT a 'zone' set
        self.assertIn("INFO:root:applying zone: None", logs.output)

    def testNXRPiShield(self, mock_k_lic, mock_k_lkc, mock_k_core, mock_subprocess):
        with patch("argparse.ArgumentParser.parse_args") as mock:

            # make the fake device and system files
            Path(self.root, "dev/ttyUSB0").touch()
            with open(Path(self.root, "sys/bus/iio/devices/iio2/name"), "w") as f:
                f.write("bme680")

            with self.assertLogs() as logs:
                mock.return_value = argparse.Namespace(
                    debug=None,
                    dry_run=True,
                    kubeconfig=None,
                    kubenode=NODE_RPI_SHIELD,
                    root=self.root,
                    manifest=NODE_MANIFEST_WSN,
                    oneshot=True,
                )
                main()
        self.assertIn(
            "INFO:root:applying resources: arm64, bme680, microphone, poe, raingauge", logs.output
        )
        self.assertIn("INFO:root:applying zone: shield", logs.output)

    def testNXRPiEnclosure(self, mock_k_lic, mock_k_lkc, mock_k_core, mock_subprocess):
        with patch("argparse.ArgumentParser.parse_args") as mock:

            # make the fake device and system files
            with open(Path(self.root, "sys/bus/iio/devices/iio2/name"), "w") as f:
                f.write("bme680")

            with self.assertLogs() as logs:
                mock.return_value = argparse.Namespace(
                    debug=None,
                    dry_run=True,
                    kubeconfig=None,
                    kubenode=NODE_RPI_ENCLOSURE,
                    root=self.root,
                    manifest=NODE_MANIFEST_WSN,
                    oneshot=True,
                )
                main()
        self.assertIn("INFO:root:applying resources: arm64, bme680, poe", logs.output)
        self.assertIn("INFO:root:applying zone: enclosure", logs.output)

    def testBladeCore(self, mock_k_lic, mock_k_lkc, mock_k_core, mock_subprocess):
        with patch("argparse.ArgumentParser.parse_args") as mock:

            # make the fake device and system files
            Path(self.root, "dev/gps").touch()
            Path(self.root, "dev/airquality").touch()
            with open(Path(self.root, "sys/bus/iio/devices/iio1/name"), "w") as f:
                f.write("bme280")

            with self.assertLogs() as logs:
                mock.return_value = argparse.Namespace(
                    debug=None,
                    dry_run=True,
                    kubeconfig=None,
                    kubenode=NODE_BLADECORE,
                    root=self.root,
                    manifest=NODE_MANIFEST_BLADE,
                    oneshot=True,
                )
                main()
        self.assertIn("INFO:root:applying resources: amd64, cuda110, gpu", logs.output)
        self.assertIn("INFO:root:applying zone: core", logs.output)

    def testMissingCompute(self, mock_k_lic, mock_k_lkc, mock_k_core, mock_subprocess):
        with patch("argparse.ArgumentParser.parse_args") as mock:
            with self.assertRaises(Exception):
                with self.assertLogs() as logs:
                    mock.return_value = argparse.Namespace(
                        debug=None,
                        dry_run=True,
                        kubeconfig=None,
                        kubenode=NODE_NONE,
                        root=self.root,
                        manifest=NODE_MANIFEST_WSN,
                        oneshot=True,
                    )
                    main()

    def testMissingHardwareFunction(self, mock_k_lic, mock_k_lkc, mock_k_core, mock_subprocess):
        with patch("argparse.ArgumentParser.parse_args") as mock:
            with self.assertLogs() as logs:
                mock.return_value = argparse.Namespace(
                    debug=None,
                    dry_run=True,
                    kubeconfig=None,
                    kubenode=NODE_RPI_ENCLOSURE,
                    root=self.root,
                    manifest=NODE_MANIFEST_HW_DETECT_FAIL,
                    oneshot=True,
                )
                main()
        combined_out = "".join(logs.output)
        self.assertIn("ERROR:root:Hardware detection function for [lidar] not found", combined_out)


if __name__ == "__main__":
    unittest.main()
