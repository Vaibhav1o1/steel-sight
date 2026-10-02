from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray

SYN_PX_PER_MM = 6
BED_X_MIN_MM = -100.0
BED_X_MAX_MM = 760.0
BED_Y_MIN_MM = -250.0
BED_Y_MAX_MM = 250.0


@dataclass(frozen=True)
class BilletSpec:
    center_mm: tuple[float, float]
    angle_deg: float
    length_mm: float
    width_mm: float
    id_text: str | None
    qr: bool
    defect: Literal["notch", "taper", "bulge", "camber"] | None
    defect_size_mm: float


@dataclass(frozen=True)
class Effects:
    brightness: float = 1.0
    gradient: float = 0.0
    noise_sigma: float = 2.0
    blur_sigma: float = 0.0
    dust: int = 0
    scale: int = 0
    glare: bool = False
    jpeg_quality: int = 90


@dataclass(frozen=True)
class CameraSpec:
    image_size: tuple[int, int] = (1920, 1080)
    fov_mm: float = 760.0
    yaw_deg: float = 0.0
    keystone: float = 0.0
    center_mm: tuple[float, float] = (290.0, 0.0)


@dataclass(frozen=True)
class SceneSpec:
    billets: tuple[BilletSpec, ...]
    camera: CameraSpec
    effects: Effects
    with_marker: bool = True


@dataclass(frozen=True)
class GroundTruthBillet:
    length_mm: float
    width_mm: float
    angle_deg: float
    center_mm: tuple[float, float]
    id_text: str | None
    qr: bool
    defect: str | None
    defect_size_mm: float


@dataclass(frozen=True)
class GroundTruth:
    h_bed_to_img: NDArray[np.float64]
    marker_corners_px: NDArray[np.float64]
    billets: tuple[GroundTruthBillet, ...]
    image_px_per_mm: float


def _build_bed_to_img(camera: CameraSpec) -> NDArray[np.float64]:
    img_w, img_h = camera.image_size
    scale = img_w / camera.fov_mm
    theta_rad = float(np.deg2rad(camera.yaw_deg))

    t_center = np.array(
        [[1.0, 0.0, -camera.center_mm[0]], [0.0, 1.0, -camera.center_mm[1]], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    r_yaw = np.array(
        [
            [np.cos(theta_rad), -np.sin(theta_rad), 0.0],
            [np.sin(theta_rad), np.cos(theta_rad), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    s_scale = np.array([[scale, 0.0, 0.0], [0.0, scale, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    k_keystone = np.array(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [camera.keystone / float(img_w), 0.0, 1.0]],
        dtype=np.float64,
    )
    t_img = np.array([[1.0, 0.0, img_w / 2.0], [0.0, 1.0, img_h / 2.0], [0.0, 0.0, 1.0]], dtype=np.float64)

    h_mat: NDArray[np.float64] = t_img @ k_keystone @ s_scale @ r_yaw @ t_center
    return h_mat


def _draw_billet_local(
    spec: BilletSpec, rng: np.random.Generator
) -> tuple[NDArray[np.uint8], NDArray[np.uint8], int, int]:
    length_px = int(round(spec.length_mm * SYN_PX_PER_MM))
    width_px = int(round(spec.width_mm * SYN_PX_PER_MM))
    pad_px = 60
    crop_w = length_px + 2 * pad_px
    crop_h = width_px + 2 * pad_px + int(round(spec.defect_size_mm * 2 * SYN_PX_PER_MM))
    cx_px = crop_w // 2
    cy_px = crop_h // 2

    n_segs = 41
    x_coords_mm = np.linspace(-spec.length_mm / 2.0, spec.length_mm / 2.0, n_segs)
    y_top_mm = np.full(n_segs, -spec.width_mm / 2.0)
    y_bottom_mm = np.full(n_segs, spec.width_mm / 2.0)

    if spec.defect == "notch":
        notch_mask = np.abs(x_coords_mm) <= 7.5
        y_top_mm[notch_mask] += spec.defect_size_mm
    elif spec.defect == "taper":
        delta_mm = (x_coords_mm / spec.length_mm) * spec.defect_size_mm
        y_top_mm -= delta_mm / 2.0
        y_bottom_mm += delta_mm / 2.0
    elif spec.defect == "bulge":
        bulge_mask = np.abs(x_coords_mm) <= 15.0
        y_top_mm[bulge_mask] -= spec.defect_size_mm
        y_bottom_mm[bulge_mask] += spec.defect_size_mm
    elif spec.defect == "camber":
        bow_mm = spec.defect_size_mm * (1.0 - (2.0 * x_coords_mm / spec.length_mm) ** 2)
        y_top_mm += bow_mm
        y_bottom_mm += bow_mm

    pts_top = np.column_stack([cx_px + x_coords_mm * SYN_PX_PER_MM, cy_px + y_top_mm * SYN_PX_PER_MM])
    pts_bottom = np.column_stack(
        [cx_px + x_coords_mm[::-1] * SYN_PX_PER_MM, cy_px + y_bottom_mm[::-1] * SYN_PX_PER_MM]
    )
    poly = np.vstack([pts_top, pts_bottom]).astype(np.int32)

    mask = np.zeros((crop_h, crop_w), dtype=np.uint8)
    cv2.fillPoly(mask, [poly], 255)

    base_grey = int(rng.integers(150, 186))
    noise_low = rng.normal(0, 5, (max(1, crop_h // 16), max(1, crop_w // 16))).astype(np.float32)
    noise_full = cv2.resize(noise_low, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)
    surface = np.clip(base_grey + noise_full, 130, 205).astype(np.uint8)
    bgr = cv2.cvtColor(surface, cv2.COLOR_GRAY2BGR)

    if spec.id_text:
        char_h_px = 0.28 * width_px
        font_scale = char_h_px / 28.0
        thickness = max(1, int(round(font_scale * 2.0)))
        text_x = int(cx_px - length_px / 2.0 + 0.35 * length_px)
        text_y = int(cy_px + char_h_px / 2.5)
        color = (245, 245, 245) if rng.random() > 0.3 else (40, 220, 240)
        cv2.putText(
            bgr,
            spec.id_text,
            (text_x, text_y),
            cv2.FONT_HERSHEY_DUPLEX,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA,
        )

    if spec.qr and spec.id_text:
        try:
            qr_enc = cv2.QRCodeEncoder.create()
            qr_raw = qr_enc.encode(spec.id_text)
            if qr_raw is not None:
                qr_border = cv2.copyMakeBorder(qr_raw, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
                qr_side_px = int(round(35.0 * SYN_PX_PER_MM))
                qr_resized = cv2.resize(qr_border, (qr_side_px, qr_side_px), interpolation=cv2.INTER_NEAREST)
                qr_x = int(cx_px - length_px / 2.0 + 0.80 * length_px - qr_side_px / 2.0)
                qr_y = int(cy_px - qr_side_px / 2.0)
                if 0 <= qr_y and qr_y + qr_side_px <= crop_h and 0 <= qr_x and qr_x + qr_side_px <= crop_w:
                    bgr[qr_y : qr_y + qr_side_px, qr_x : qr_x + qr_side_px] = cv2.cvtColor(
                        qr_resized, cv2.COLOR_GRAY2BGR
                    )
        except Exception:
            pass

    return np.asarray(bgr, dtype=np.uint8), mask, cx_px, cy_px


def _apply_effects(img: NDArray[np.uint8], effects: Effects, rng: np.random.Generator) -> NDArray[np.uint8]:
    out = img.astype(np.float32)

    if effects.brightness != 1.0:
        out = out * effects.brightness

    if effects.gradient > 0.0:
        img_w = out.shape[1]
        falloff = 1.0 - effects.gradient * (np.arange(img_w, dtype=np.float32) / float(img_w))
        out = out * falloff[None, :, None]

    out_u8 = np.clip(out, 0, 255).astype(np.uint8)

    if effects.dust > 0:
        h, w = out_u8.shape[:2]
        xs = rng.integers(0, w, size=effects.dust)
        ys = rng.integers(0, h, size=effects.dust)
        colors = rng.choice([0, 255], size=effects.dust)
        for x, y, c in zip(xs, ys, colors, strict=False):
            cv2.circle(out_u8, (int(x), int(y)), int(rng.integers(1, 3)), int(c), -1)

    if effects.glare:
        h, w = out_u8.shape[:2]
        gx, gy = int(rng.integers(w // 4, 3 * w // 4)), int(rng.integers(h // 3, 2 * h // 3))
        overlay = out_u8.copy()
        cv2.ellipse(overlay, (gx, gy), (180, 70), int(rng.integers(-20, 20)), 0, 360, (255, 255, 255), -1)
        out_u8 = cv2.addWeighted(overlay, 0.75, out_u8, 0.25, 0.0)

    if effects.noise_sigma > 0.0:
        noise = rng.normal(0, effects.noise_sigma, out_u8.shape).astype(np.float32)
        out_u8 = np.clip(out_u8.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    if effects.blur_sigma > 0.0:
        k = int(np.ceil(effects.blur_sigma * 3.0)) * 2 + 1
        out_u8 = cv2.GaussianBlur(out_u8, (k, k), effects.blur_sigma)

    if 0 < effects.jpeg_quality < 100:
        success, enc = cv2.imencode(".jpg", out_u8, [cv2.IMWRITE_JPEG_QUALITY, effects.jpeg_quality])
        if success and enc is not None:
            dec = cv2.imdecode(enc, cv2.IMREAD_COLOR)
            if dec is not None:
                out_u8 = dec

    return np.asarray(out_u8, dtype=np.uint8)


def render_scene(spec: SceneSpec, rng: np.random.Generator) -> tuple[NDArray[np.uint8], GroundTruth]:
    canvas_w = int(round((BED_X_MAX_MM - BED_X_MIN_MM) * SYN_PX_PER_MM))
    canvas_h = int(round((BED_Y_MAX_MM - BED_Y_MIN_MM) * SYN_PX_PER_MM))
    bed_canvas = np.full((canvas_h, canvas_w, 3), 28, dtype=np.uint8)

    if spec.effects.scale > 0 and len(spec.billets) > 0:
        pass  # will be drawn with billets

    if spec.with_marker:
        marker_side_px = int(round(80.0 * SYN_PX_PER_MM))
        border_px = int(round(10.0 * SYN_PX_PER_MM))
        mcx = int(round((0.0 - BED_X_MIN_MM) * SYN_PX_PER_MM))
        mcy = int(round((0.0 - BED_Y_MIN_MM) * SYN_PX_PER_MM))
        half_total = marker_side_px // 2 + border_px
        bed_canvas[
            mcy - half_total : mcy + half_total,
            mcx - half_total : mcx + half_total,
        ] = 255
        aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, 0, marker_side_px)
        half_m = marker_side_px // 2
        bed_canvas[mcy - half_m : mcy + half_m, mcx - half_m : mcx + half_m] = cv2.cvtColor(
            marker_img, cv2.COLOR_GRAY2BGR
        )

    for b in spec.billets:
        billet_bgr, mask_img, cx_loc, cy_loc = _draw_billet_local(b, rng)

        if spec.effects.scale > 0:
            for _ in range(spec.effects.scale):
                sx = int(rng.integers(0, billet_bgr.shape[1]))
                sy = int(rng.integers(0, billet_bgr.shape[0]))
                if mask_img[sy, sx] > 0:
                    cv2.circle(
                        billet_bgr,
                        (sx, sy),
                        int(rng.integers(10, 30)),
                        (int(rng.integers(50, 90)), int(rng.integers(50, 90)), int(rng.integers(50, 90))),
                        -1,
                    )

        bed_bx = (b.center_mm[0] - BED_X_MIN_MM) * SYN_PX_PER_MM
        bed_by = (b.center_mm[1] - BED_Y_MIN_MM) * SYN_PX_PER_MM
        m_rot = cv2.getRotationMatrix2D((float(cx_loc), float(cy_loc)), float(-b.angle_deg), 1.0)
        m_rot[0, 2] += bed_bx - float(cx_loc)
        m_rot[1, 2] += bed_by - float(cy_loc)

        warped_billet = cv2.warpAffine(billet_bgr, m_rot, (canvas_w, canvas_h))
        warped_mask = cv2.warpAffine(mask_img, m_rot, (canvas_w, canvas_h))
        active_pix = warped_mask > 0
        bed_canvas[active_pix] = warped_billet[active_pix]

    h_bed_to_img = _build_bed_to_img(spec.camera)
    m_canvas_to_bed = np.array(
        [[1.0 / SYN_PX_PER_MM, 0.0, BED_X_MIN_MM], [0.0, 1.0 / SYN_PX_PER_MM, BED_Y_MIN_MM], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    h_canvas_to_img = h_bed_to_img @ m_canvas_to_bed

    warped_img = np.asarray(
        cv2.warpPerspective(
            bed_canvas,
            h_canvas_to_img,
            spec.camera.image_size,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(28, 28, 28),
        ),
        dtype=np.uint8,
    )

    final_img = _apply_effects(warped_img, spec.effects, rng)

    offset_mm = 0.5 / float(SYN_PX_PER_MM)
    corners_bed = np.array(
        [
            [-40.0 - offset_mm, -40.0 - offset_mm, 1.0],
            [40.0 - offset_mm, -40.0 - offset_mm, 1.0],
            [40.0 - offset_mm, 40.0 - offset_mm, 1.0],
            [-40.0 - offset_mm, 40.0 - offset_mm, 1.0],
        ],
        dtype=np.float64,
    )
    gt_corners_hom = (h_bed_to_img @ corners_bed.T).T
    marker_corners_px = gt_corners_hom[:, :2] / gt_corners_hom[:, 2:]

    scale = spec.camera.image_size[0] / spec.camera.fov_mm
    gt_billets = tuple(
        GroundTruthBillet(
            length_mm=b.length_mm,
            width_mm=b.width_mm,
            angle_deg=b.angle_deg,
            center_mm=b.center_mm,
            id_text=b.id_text,
            qr=b.qr,
            defect=b.defect,
            defect_size_mm=b.defect_size_mm,
        )
        for b in spec.billets
    )

    gt = GroundTruth(
        h_bed_to_img=h_bed_to_img,
        marker_corners_px=marker_corners_px,
        billets=gt_billets,
        image_px_per_mm=float(scale),
    )
    return final_img, gt


def random_scene(rng: np.random.Generator, variant: str = "clean") -> SceneSpec:
    effects_map = {
        "clean": Effects(),
        "dim": Effects(brightness=0.6),
        "bright": Effects(brightness=1.35),
        "gradient": Effects(gradient=0.35),
        "noise": Effects(noise_sigma=7.0),
        "blur": Effects(blur_sigma=1.2),
        "dust": Effects(dust=60),
        "scale": Effects(scale=8),
        "glare": Effects(glare=True),
    }
    effects = effects_map.get(variant, Effects())

    n_billets = 1 if rng.random() > 0.35 else 2
    billets: list[BilletSpec] = []

    for i in range(n_billets):
        if n_billets == 1:
            length_mm = float(rng.uniform(300.0, 520.0))
            center_x_mm = float(rng.uniform(300.0, 420.0))
        else:
            length_mm = float(rng.uniform(220.0, 270.0))
            center_x_mm = float(160.0 + i * 270.0)

        width_mm = float(rng.uniform(80.0, 115.0))
        angle_deg = float(rng.uniform(-20.0, 20.0))
        center_y_mm = float(rng.uniform(-30.0, 30.0))

        letter = str(rng.choice(list("ABCDEFGHJKLMNPRSTUVWXYZ")))
        id_num1 = int(rng.integers(10, 100))
        id_num2 = int(rng.integers(1000, 10000))
        id_text = f"{letter}{id_num1:02d}-{id_num2:04d}"

        qr = bool(rng.random() < 0.5)
        has_defect = bool(rng.random() < 0.3)
        defect: Literal["notch", "taper", "bulge", "camber"] | None = None
        defect_size_mm = 0.0
        if has_defect:
            defect = rng.choice(["notch", "taper", "bulge", "camber"])
            defect_size_mm = float(rng.uniform(6.0, 10.0))

        billets.append(
            BilletSpec(
                center_mm=(center_x_mm, center_y_mm),
                angle_deg=angle_deg,
                length_mm=length_mm,
                width_mm=width_mm,
                id_text=id_text,
                qr=qr,
                defect=defect,
                defect_size_mm=defect_size_mm,
            )
        )

    return SceneSpec(
        billets=tuple(billets),
        camera=CameraSpec(),
        effects=effects,
        with_marker=True,
    )
