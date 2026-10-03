# ODIN mounting work

The camera models and webcam housing dimensions are unknown. `adjustable_base.scad` is an editable **fixture base**, not a fitted camera carrier or validated final assembly. It starts at the overview's 80 x 40 x 3 mm envelope and provides six adjustment/strap slots. There is no assumed Pi PCB, camera PCB or webcam screw pattern.

## CAD lead's next steps

1. Open the base in OpenSCAD and inspect the dimensions. Increase the envelope if the measured camera housings need it.
2. Measure the NoIR PCB outline, hole-center distances, screw diameter/clearance, component height, lens center and ribbon exit. Use the exact variant's official mechanical drawing and confirm with the physical part. The overview's 24 x 25 mm / 21 x 20 mm figures must not be assumed for every camera variant.
3. Measure the USB webcam housing, lens center, cable exit, existing mount and focus access. A universal webcam hole pattern does not exist.
4. Add separate carriers or a clamp appropriate to those measured parts. Use standoffs for the camera board, washers and a stable removable fixture. Do not use the bare sensor PCB as a strap-bearing surface.
5. Set optical-axis spacing from the lens centers. Aim for <25 mm when feasible, parallel axes and similar lens height. Housing dimensions may prevent the spacing target; record the actual baseline instead of forcing interference.
6. Check camera field of view, cable bend clearance, access to connectors/focus, electrical isolation, balance and rigidity. A tripod interface needs its own measured threaded insert/fastener; none is included in the base.
7. Render in OpenSCAD (F6), export STL and inspect in the slicer. A starting PLA profile is 0.2 mm layers, 3 walls and 30% infill, subject to printer/material and load testing. Print a fit coupon or provisional base before committing to camera-specific carriers.
8. Assemble, focus, lock positions and relieve cable strain. Perform geometric calibration only after the fixture is stable. Check alignment again after transport.

## Parameters

All dimensions are millimeters. The base has a centered XY outline and its bottom at Z=0. Slots are 12 mm overall length x 3.2 mm width by default. Their centers are x=-26, 0, 26 and y=-12, 12; the OpenSCAD file derives those from plate size. These are fixture slots, not claimed camera mounting holes.

Example export if OpenSCAD is installed:

```bash
openscad -o adjustable_base.stl adjustable_base.scad
```

The SCAD source has dimensional assertions but has not been compiled or physically fit-tested in this session. There is deliberately no print-ready camera carrier until the real dimensions are available.

Reference: [official Raspberry Pi camera models and installation](https://www.raspberrypi.com/documentation/accessories/camera.html). Download the mechanical drawing for the confirmed model before placing PCB holes.
