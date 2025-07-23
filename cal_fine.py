#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Hybrid STEP volume calculator:
1) Try sewing → solid volume (exact).
2) If that fails, fall back to voxel approximation.

Requirements:
    pip install pythonocc-core pyvista numpy
"""

import os, sys, argparse, tempfile
import numpy as np
import pyvista as pv

# --- pythonOCC core ---
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_SHELL
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepGProp import brepgprop_VolumeProperties
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib_Add
from OCC.Extend.DataExchange import write_stl_file

# ---------- helpers ----------
def read_step_shape(path):
    rdr = STEPControl_Reader()
    if rdr.ReadFile(path) != IFSelect_RetDone:
        raise RuntimeError(f"STEP read failed: {path}")
    rdr.TransferRoots()
    return rdr.Shape()


def sewing_to_solids(shape, tol=0.05):
    """
    봉합(Sewing) 후 얻은 TopoDS_Solid 리스트를 반환.
    실패하면 빈 리스트를 돌려줍니다.
    """
    sewer = BRepBuilderAPI_Sewing(tol)
    sewer.Add(shape)
    sewer.Perform()
    sewed = sewer.SewedShape()

    solids = []

    # ① 이미 SOLID가 있는지 탐색
    exp = TopExp_Explorer(sewed, TopAbs_SOLID)
    while exp.More():
        solids.append(exp.Current())
        exp.Next()

    if solids:
        return solids

    # ② SOLID가 없으면 SHELL → SOLID 변환 시도
    exp = TopExp_Explorer(sewed, TopAbs_SHELL)
    while exp.More():
        shell = exp.Current()
        maker = BRepBuilderAPI_MakeSolid(shell)
        if maker.IsDone():
            solids.append(maker.Solid())
        exp.Next()

    return solids

def solids_volume(solids, unit_scale=1.0):
    """Return list[(id, vol_mm3, COM)], and total."""
    results, total = [], 0.0
    for idx, solid in enumerate(solids):
        props = GProp_GProps()
        brepgprop_VolumeProperties(solid, props)
        vm = props.Mass() * unit_scale
        com = props.CentreOfMass()
        results.append((idx, vm, (com.X(), com.Y(), com.Z())))
        total += vm
    return results, total

def bbox_volume_mm3(shape):
    box = Bnd_Box()
    brepbndlib_Add(shape, box, True)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (xmin, ymin, zmin, xmax, ymax, zmax, (xmax-xmin)*(ymax-ymin)*(zmax-zmin))

def shape_to_pv_mesh(shape):
    """Quick path: write tmp STL then read via PyVista."""
    with tempfile.TemporaryDirectory() as td:
        tmp_stl = os.path.join(td, "t.stl")
        write_stl_file(shape, tmp_stl)
        mesh = pv.read(tmp_stl)
    return mesh

def voxel_volume(mesh, pitch):
    tri = mesh.triangulate()
    vox = tri.voxelize(density=pitch)
    vol_mm3 = vox.n_cells * pitch**3
    return vox, vol_mm3

UNIT = {"mm3":1.0, "cm3":1/1_000, "m3":1/1_000_000_000}

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser("Hybrid STEP volume")
    ap.add_argument("--step", required=True, help="STEP file")
    ap.add_argument("--tol", type=float, default=0.05, help="Sewing tolerance (mm)")
    ap.add_argument("--pitch", type=float, default=0.5, help="Voxel pitch (mm)")
    ap.add_argument("--unit", choices=UNIT.keys(), default="cm3", help="Output unit")
    ap.add_argument("--show", action="store_true", help="Show mesh + voxels")
    ap.add_argument("--bbox", action="store_true", help="Print bounding-box volume")
    args = ap.parse_args()

    if not os.path.exists(args.step):
        print("STEP file not found.", file=sys.stderr); sys.exit(1)

    print(f"[READ] {args.step}")
    shape = read_step_shape(args.step)

    # Bounding box (optional)
    if args.bbox:
        *minmax, bbox_mm3 = bbox_volume_mm3(shape)
        print(f"[BBox] volume = {bbox_mm3*UNIT[args.unit]:.6f} {args.unit}")

    # 1) 정확 시도
    print(f"[Sew] tol={args.tol} mm ...")
    solids = sewing_to_solids(shape, tol=args.tol)
    if solids:
        infos, total = solids_volume(solids, UNIT[args.unit])
        print(f"[OK] closed solids found = {len(infos)}")
        for idx, v, com in infos:
            print(f"  • Solid {idx}: {v:.6f} {args.unit} (COM {com})")
        print(f"  Σ Total: {total:.6f} {args.unit}")
        return

    print("[WARN] No closed solid after sewing. Falling back to voxel...")

    # 2) Voxel 근사
    mesh = shape_to_pv_mesh(shape)
    vox, vol_mm3 = voxel_volume(mesh, args.pitch)
    print(f"[Voxel] pitch={args.pitch} mm → {vol_mm3*UNIT[args.unit]:.6f} {args.unit}")

    if args.show:
        p = pv.Plotter()
        p.add_mesh(mesh, color="lightgray", opacity=0.35, name="mesh")
        p.add_mesh(vox, color="red", opacity=0.5, name="voxel")
        p.show()

if __name__ == "__main__":
    main()
