import os
import sys
import argparse
import pyvista as pv

# --- PythonOCC 관련 모듈 ---
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TopoDS import topods_Face
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Extend.DataExchange import write_stl_file

from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib_Add


def compute_bbox_volume(step_filename: str):
    """STEP 파일 전체의 Axis‑Aligned Bounding Box와 그 부피를 반환합니다."""
    reader = STEPControl_Reader()
    if reader.ReadFile(step_filename) != IFSelect_RetDone:
        raise RuntimeError(f"STEP 파일 읽기 실패: {step_filename}")

    reader.TransferRoots()
    shape = reader.Shape()

    bbox = Bnd_Box()
    # tolerance=True 로 디노이즈된 box, triangulate=False (정밀)
    brepbndlib_Add(shape, bbox, True)

    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    volume = dx * dy * dz
    return (xmin, ymin, zmin, xmax, ymax, zmax, volume)

def export_step_faces_to_stl(step_filename: str, out_dir: str = "faces_out") -> list:
    """
    STEP 파일에서 Face(면)를 하나씩 추출하여, 
    out_dir 디렉터리에 face_0.stl, face_1.stl, ... 형태로 저장합니다.
    저장된 STL 파일들의 경로 리스트를 반환합니다.
    """
    reader = STEPControl_Reader()
    status = reader.ReadFile(step_filename)
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP 파일을 읽는 데 실패했습니다: {step_filename}")

    # STEP 파일을 Shape 객체로 변환
    reader.TransferRoots()
    shape = reader.Shape()

    # 출력 디렉터리 생성
    os.makedirs(out_dir, exist_ok=True)

    # STEP 파일 내 모든 Face를 순회하여 개별 STL 파일로 저장
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    face_index = 0
    out_filenames = []
    while exp.More():
        face = topods_Face(exp.Current())
        out_filename = os.path.join(out_dir, f"face_{face_index}.stl")
        write_stl_file(face, out_filename)
        out_filenames.append(out_filename)
        print(f"{out_filename} 저장 완료.")
        face_index += 1
        exp.Next()

    return out_filenames

def load_and_view_faces(stl_files: list):
    """
    추출된 STL 파일들을 PyVista로 로딩하여 3D 뷰어를 띄웁니다.
    마우스 클릭 시, 해당 면만 파란색(불투명, Depth Test 해제, 에지 비활성화)으로 하이라이트되고,
    이전 선택은 원래 상태로 복구됩니다.
    """
    if not stl_files:
        print("STL 파일이 없습니다.")
        return

    plotter = pv.Plotter()

    # 각 STL 파일을 읽어 pickable한 메쉬로 추가합니다.
    for stl_file in stl_files:
        mesh = pv.read(stl_file)
        plotter.add_mesh(
            mesh,
            show_edges=True,
            pickable=True,
            name=stl_file  # 이름은 파일명을 사용
        )

    # 하이라이트를 위해 추가된 메쉬를 관리할 고정 actor 이름
    highlight_actor_name = "highlight_actor"

    def mesh_pick_callback(picked_mesh):
        # 이전에 하이라이트된 actor 제거
        try:
            plotter.remove_actor(highlight_actor_name)
        except Exception:
            pass

        # 새로 선택된 면이 있으면 파란색으로 하이라이트 추가 (에지는 보이지 않도록 설정)
        if picked_mesh is not None:
            actor = plotter.add_mesh(
                picked_mesh,
                color='blue',       # 하이라이트 색상을 파란색으로 변경
                opacity=1.0,        # 완전 불투명
                show_edges=False,   # 에지(선) 비활성화
                name=highlight_actor_name
            )
            # Depth Test를 비활성화하여 항상 최상단에 표시되도록 함
            actor.GetProperty().SetDepthTest(False)
            print("선택된 면이 파란색으로 하이라이트되었습니다.")
        else:
            print("메쉬가 선택되지 않았습니다.")

    # 메쉬 피킹 활성화 (한 번에 하나의 메쉬만 선택)
    plotter.enable_mesh_picking(
        callback=mesh_pick_callback,
        show_message=True,
        multi=False
    )

    print("[안내] 3D 창에서 마우스 왼쪽 드래그로 회전, 휠로 줌, 'P' 키로 픽 모드를 토글할 수 있습니다.")
    plotter.show()

def main():
    parser = argparse.ArgumentParser(
        description="STEP 파일의 Bounding‑Box 부피 계산 + 단위 변환"
    )
    parser.add_argument("--step", type=str, default="test.STEP",
                        help="대상 STEP 파일 경로")
    parser.add_argument("--out", type=str, default="faces_out",
                        help="면별 STL을 저장할 디렉터리")
    parser.add_argument(
        "--unit",
        choices=["mm3", "cm3", "m3"],
        default="cm3",
        help="출력 부피 단위 (mm3 / cm3 / m3)"
    )

    # 1️⃣ 인자 파싱
    args = parser.parse_args()

    # 2️⃣ 단위 환산 계수
    scale = {"mm3": 1.0, "cm3": 1.0 / 1_000, "m3": 1.0 / 1_000_000_000}[args.unit]

    step_file = args.step
    if not os.path.exists(step_file):
        print(f"입력 STEP 파일이 존재하지 않습니다: {step_file}")
        sys.exit(1)

    # 3️⃣ Bounding‑Box 부피 계산
    xmin, ymin, zmin, xmax, ymax, zmax, vol_mm3 = compute_bbox_volume(step_file)
    vol_conv = vol_mm3 * scale

    # 4️⃣ 결과 표시
    print("\n[Bounding Box]")
    print(f"  x: {xmin:.3f} – {xmax:.3f}")
    print(f"  y: {ymin:.3f} – {ymax:.3f}")
    print(f"  z: {zmin:.3f} – {zmax:.3f}")
    print(f"  Volume: {vol_conv:.6f} {args.unit}")


if __name__ == "__main__":
    main()