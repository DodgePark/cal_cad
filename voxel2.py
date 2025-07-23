import os
import sys
import argparse
import pyvista as pv
import numpy as np

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Extend.DataExchange import read_step_file


def voxel_volume(step_path: str, pitch: float = 0.5, unit_scale: float = 1.0):
    """
    STEP 파일을 읽어 voxelize 후 부피를 근사 계산.
    
    Args:
        step_path (str): STEP 파일 경로.
        pitch (float): voxel 격자 크기 (mm 단위).
        unit_scale (float): 결과 부피 단위 변환 계수.
                            (예: mm³→cm³ = 1/1000)
    
    Returns:
        (float): 근사 부피.
    """
    # STEP 파일을 pyvista 메쉬로 변환
    surface = pv.wrap(read_step_file(step_path).triangulate())

    # Voxelization
    print(f"[INFO] Voxelizing with pitch={pitch}mm ...")
    vox = surface.voxelize(density=pitch)

    # Voxel 개수로 부피 근사
    vol_mm3 = vox.n_cells * (pitch ** 3)
    vol = vol_mm3 * unit_scale
    return vol, vox


def visualize_voxel(vox):
    """
    Voxelized 메쉬를 시각화
    """
    plotter = pv.Plotter()
    plotter.add_mesh(vox, color='orange', show_edges=False)
    plotter.show()


def main():
    parser = argparse.ArgumentParser(description="STEP 파일을 Voxel 기반으로 부피 근사 계산")
    parser.add_argument("--step", type=str, default="test.STEP", help="대상 STEP 파일 경로")
    parser.add_argument("--pitch", type=float, default=0.5, help="voxel 크기(mm)")
    parser.add_argument("--unit", choices=["mm3", "cm3", "m3"], default="cm3",
                        help="결과 부피 단위")
    parser.add_argument("--view", action="store_true", help="voxelized 메쉬 시각화 여부")
    args = parser.parse_args()

    step_file = args.step
    pitch = args.pitch

    if not os.path.exists(step_file):
        print(f"[ERROR] STEP 파일이 존재하지 않습니다: {step_file}")
        sys.exit(1)

    # 단위 변환 계수
    unit_scale = {"mm3": 1.0, "cm3": 1/1000, "m3": 1/1_000_000_000}[args.unit]

    print(f"[INFO] STEP 파일: {step_file}")
    print(f"[INFO] Voxel Pitch: {pitch} mm")
    print(f"[INFO] Target Unit: {args.unit}")

    vol, vox = voxel_volume(step_file, pitch=pitch, unit_scale=unit_scale)

    print(f"\n[결과] 근사 부피: {vol:.3f} {args.unit}")

    if args.view:
        visualize_voxel(vox)


if __name__ == "__main__":
    main()
