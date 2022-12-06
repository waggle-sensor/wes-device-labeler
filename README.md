# Device Labeler

The [WES](https://github.com/waggle-sensor/waggle-edge-stack) device labeler is responsible for applying Kubernetes "labels" to the compute nodes based upon sensor/resource availability to assist the Kubernetes scheduler to place pods on the correct compute units. For example, if the "microphone" is physically connected to a Raspberry Pi compute unit, it labels that Raspberry Pi with the `resource.microphone` label.

## How it works

The device labeler reads the [Waggle node's manifest](https://auth.sagecontinuum.org/manifests/) [ConfigMap](https://auth.sagecontinuum.org/manifests/) and then applies 3 items to the kubernetes compute node (ex. `000048b02d0766be.ws-nxcore`) labels.

1. the compute unit's hardware capabilities (ex. `gpu`, `arm64`, `cuda102`) [added as `resource.*`]
2. the list of connected sensors [added as `resource.*`]
3. the compute unit's `zone` (ex. `shield`) [added as `zone.*`]

> The list of connected sensors are verified to ensure the physical hardware sensor is available. If the hardware is not found the `resource.*` label for that sensor is **NOT** applied.
