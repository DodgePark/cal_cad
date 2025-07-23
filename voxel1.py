#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Voxel approximation volume calculator for (possibly open) STEP geometry.

Requirements:
    pip install pythonocc-core pyvista numpy

Usage:
    python step_voxel_volume.py --step my_part.step --pitch 0.5 --unit cm3 --show
"""

import os
import sys
import argparse
import numpy as np
import pyvista as pv

# pythonOCC
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib_Add

# ------------------------------------------------------------------
# I/O: Read STEP -> TopoDS_Shape
# ------------------------------------------------------------------
def read_step_shape(path: str):
    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise RuntimeError(f"STEP read failed: {path}")
    reader.TransferRoots()
    return reader.Shape()

# ------------------------------------------------------------------
# Bounding box (optional, for reference / sanity check)
# ------------------------------------------------------------------
def shape_bbox_mm3(shape):
    box = Bnd_Box()
    brepbndlib_Add(shape, box, True)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    vol = dx * dy * dz
    return (xmin, ymin, zmin, xmax, ymax, zmax, vol)

# ------------------------------------------------------------------
# Convert TopoDS_Shape -> PyVista PolyData (triangulated surface)
# We go via pythonOCC's "read_step_shape" + pyvista wrap helper.
# ------------------------------------------------------------------
def shape_to_pv_mesh(shape):
    # pyvista가 직접 TopoDS를 읽지 못하므로 pythonOCC -> STL string roundtrip은 무겁다.
    # 간단히 pyvista.OCCReader 가 있다면 사용, 없으면 OCC->mesh triangulation util 사용.
    #
    # PyVista는 vtk 기반이므로, pythonOCC의 meshing을 거쳐 points/faces를 뽑는 헬퍼가 필요.
    # 최소 구현: export 임시 STL 후 pv.read().  (속도 느리지만 안정적)
    import tempfile
    from OCC.Extend.DataExchange import write_stl_file

    with tempfile.TemporaryDirectory() as td:
        tmp_stl = os.path.join(td, "tmp.stl")
        write_stl_file(shape, tmp_stl)
        mesh = pv.read(tmp_stl)
    return mesh

# ------------------------------------------------------------------
# Voxel volume
# ------------------------------------------------------------------
def voxel_volume_mm3(mesh: pv.PolyData, pitch: float):
    """
    mesh: PyVista PolyData (assumed mm units)
    pitch: voxel edge length in same units (e.g., mm)

    Returns: (voxelized_grid, volume_mm3)
    """
    # Ensure surface is triangularized
    tri = mesh.triangulate()
    # voxelize() density param: approximate target cell size in same units
    vox = tri.voxelize(density=pitch)
    # Some voxel cells may be masked; count active cells
    n_cells = vox.n_cells
    vol = (pitch ** 3) * n_cells
    return vox, vol

# ------------------------------------------------------------------
# Unit conversion helpers
# ------------------------------------------------------------------
UNIT_SCALE = {
    "mm3": 1.0,
    "cm3": 1.0 / 1000.0,               # 1 cm³ = 1000 mm³
    "m3": 1.0 / 1_000_000_000.0,       # 1 m³ = 1e9 mm³
}

def convert_volume(vol_mm3: float, unit: str) -> float:
    return vol_mm3 * UNIT_SCALE[unit]

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Voxel-approx volume from (possibly open) STEP.")
    ap.add_argument("--step", required=True, help="STEP file path")
    ap.add_argument("--pitch", type=float, default=1.0,
                    help="Voxel edge length in model units (mm if STEP in mm). Smaller = finer, slower.")
    ap.add_argument("--unit", choices=["mm3", "cm3", "m3"], default="cm3",
                    help="Output volume unit.")
    ap.add_argument("--show", action="store_true",
                    help="Visualize original mesh + voxel grid.")
    ap.add_argument("--bbox", action="store_true",
                    help="Also print axis-aligned bounding-box volume.")
    args = ap.parse_args()

    step_path = args.step
    if not os.path.exists(step_path):
        print(f"STEP file not found: {step_path}", file=sys.stderr)
        sys.exit(1)

    # Read STEP
    print(f"[INFO] Reading STEP: {step_path}")
    shape = read_step_shape(step_path)

    # Bounding box (optional)
    if args.bbox:
        xmin, ymin, zmin, xmax, ymax, zmax, bbox_vol_mm3 = shape_bbox_mm3(shape)
        bbox_vol_conv = convert_volume(bbox_vol_mm3, args.unit)
        print("\n[Bounding Box]")
        print(f"  x: {xmin:.3f} – {xmax:.3f}")
        print(f"  y: {ymin:.3f} – {ymax:.3f}")
        print(f"  z: {zmin:.3f} – {zmax:.3f}")
        print(f"  Volume({args.unit}): {bbox_vol_conv:.6f}")

    # Shape -> PyVista
    print("[INFO] Converting shape to mesh...")
    mesh = shape_to_pv_mesh(shape)
    if mesh.n_points == 0:
        print("ERROR: Empty mesh extracted.", file=sys.stderr)
        sys.exit(2)

    # Voxel volume
    print(f"[INFO] Voxelizing @ pitch={args.pitch} ...")
    vox, vol_mm3 = voxel_volume_mm3(mesh, pitch=args.pitch)
    vol_conv = convert_volume(vol_mm3, args.unit)

    print("\n[Voxel Volume Approximation]")
    print(f"  Pitch: {args.pitch} (model units)")
    print(f"  Cells: {vox.n_cells}")
    print(f"  Volume: {vol_conv:.6f} {args.unit}")

    # Visualization
    if args.show:
        print("[INFO] Launching viewer...")
        p = pv.Plotter()
        p.add_mesh(mesh, color="lightgray", opacity=0.4, show_edges=False, name="original")
        p.add_mesh(vox, color="red", opacity=0.5, show_edges=False, name="voxels")
        p.show()


if __name__ == "__main__":
    main()
