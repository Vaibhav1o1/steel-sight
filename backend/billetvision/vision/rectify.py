from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision.schemas import Roi
from billetvision.vision.types import Calibration


class Rectifier:
    """Handles perspective rectification and coordinate transformations."""

    def __init__(
        self,
        cal: Calibration,
        size: tuple[int, int],
        m_img_to_rect: NDArray[np.float64] | None = None,
        m_rect_to_img: NDArray[np.float64] | None = None,
        map_x: NDArray[np.float32] | None = None,
        map_y: NDArray[np.float32] | None = None,
    ) -> None:
        self.cal = cal
        self.roi = cal.roi
        self.rect_px_per_mm = cal.rect_px_per_mm
        self.size = size
        self.m_img_to_rect = m_img_to_rect
        self.m_rect_to_img = m_rect_to_img
        self.map_x = map_x
        self.map_y = map_y

    def apply(self, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
        """Rectify a raw camera frame into the conveyor ROI plane."""
        if self.map_x is not None and self.map_y is not None:
            return cv2.remap(frame, self.map_x, self.map_y, interpolation=cv2.INTER_LINEAR)

        if self.m_img_to_rect is not None:
            return cv2.warpPerspective(
                frame,
                self.m_img_to_rect,
                self.size,
                flags=cv2.INTER_LINEAR,
            )

        raise ValueError("Rectifier not properly initialized with matrix or maps")

    def rect_to_image(self, points_px: NDArray[np.float64]) -> NDArray[np.float64]:
        """Transform points from rectified pixel coordinates back to raw camera frame pixels.

        Accepts shape (N, 2) or (2,). Returns shape (N, 2) or (2,).
        """
        pts = np.asarray(points_px, dtype=np.float64)
        is_single = pts.ndim == 1
        if is_single:
            pts = pts.reshape(1, 2)

        if self.m_rect_to_img is not None:
            n = len(pts)
            pts_hom = np.column_stack([pts, np.ones(n, dtype=np.float64)])
            mapped_hom = (self.m_rect_to_img @ pts_hom.T).T
            w = np.maximum(np.abs(mapped_hom[:, 2:]), 1e-9)
            res = mapped_hom[:, :2] / w
            return res[0] if is_single else res

        # With intrinsics: rect px -> bed mm -> undistorted px -> distorted px
        r = self.rect_px_per_mm
        roi = self.roi
        x_bed = pts[:, 0] / r + roi.x0_mm
        y_bed = pts[:, 1] / r + roi.y0_mm
        pts_bed_hom = np.column_stack([x_bed, y_bed, np.ones(len(pts), dtype=np.float64)])

        h_bed_to_img = np.linalg.inv(self.cal.h_img_to_bed)
        pts_undist_hom = (h_bed_to_img @ pts_bed_hom.T).T
        w = np.maximum(np.abs(pts_undist_hom[:, 2:]), 1e-9)
        x_u = pts_undist_hom[:, 0] / w.ravel()
        y_u = pts_undist_hom[:, 1] / w.ravel()

        if self.cal.camera_matrix is not None and self.cal.dist_coeffs is not None:
            fx = float(self.cal.camera_matrix[0, 0])
            fy = float(self.cal.camera_matrix[1, 1])
            cx = float(self.cal.camera_matrix[0, 2])
            cy = float(self.cal.camera_matrix[1, 2])

            xn = (x_u - cx) / fx
            yn = (y_u - cy) / fy
            r2 = xn * xn + yn * yn
            r4 = r2 * r2
            r6 = r4 * r2

            d = self.cal.dist_coeffs.ravel()
            k1 = float(d[0]) if len(d) > 0 else 0.0
            k2 = float(d[1]) if len(d) > 1 else 0.0
            p1 = float(d[2]) if len(d) > 2 else 0.0
            p2 = float(d[3]) if len(d) > 3 else 0.0
            k3 = float(d[4]) if len(d) > 4 else 0.0

            alpha = 1.0 + k1 * r2 + k2 * r4 + k3 * r6
            dx = 2.0 * p1 * xn * yn + p2 * (r2 + 2.0 * xn * xn)
            dy = p1 * (r2 + 2.0 * yn * yn) + 2.0 * p2 * xn * yn

            x_dist = fx * (xn * alpha + dx) + cx
            y_dist = fy * (yn * alpha + dy) + cy
            res = np.column_stack([x_dist, y_dist])
            return res[0] if is_single else res

        res = np.column_stack([x_u, y_u])
        return res[0] if is_single else res


def build_rectifier(cal: Calibration) -> Rectifier:
    """Precompute perspective transform or remap tables for the given calibration."""
    roi: Roi = cal.roi
    r: float = cal.rect_px_per_mm
    w_px = int(round(roi.w_mm * r))
    h_px = int(round(roi.h_mm * r))
    size = (w_px, h_px)

    has_intrinsics = (
        cal.camera_matrix is not None and cal.dist_coeffs is not None and np.any(cal.dist_coeffs != 0.0)
    )

    if not has_intrinsics:
        # S: scale mm -> rect px
        s_mat = np.array([[r, 0.0, 0.0], [0.0, r, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
        # T: translate bed origin to ROI top-left
        t_mat = np.array([[1.0, 0.0, -roi.x0_mm], [0.0, 1.0, -roi.y0_mm], [0.0, 0.0, 1.0]], dtype=np.float64)
        m_img_to_rect = s_mat @ t_mat @ cal.h_img_to_bed
        m_rect_to_img = np.linalg.inv(m_img_to_rect)

        return Rectifier(
            cal=cal,
            size=size,
            m_img_to_rect=m_img_to_rect,
            m_rect_to_img=m_rect_to_img,
        )

    # With intrinsics: precompute remap from rect px -> distorted image px
    u_grid, v_grid = np.meshgrid(
        np.arange(w_px, dtype=np.float32),
        np.arange(h_px, dtype=np.float32),
    )
    x_bed = (u_grid / r + roi.x0_mm).astype(np.float64)
    y_bed = (v_grid / r + roi.y0_mm).astype(np.float64)
    pts_bed_hom = np.stack(
        [x_bed.ravel(), y_bed.ravel(), np.ones(w_px * h_px, dtype=np.float64)],
        axis=1,
    )

    h_bed_to_img = np.linalg.inv(cal.h_img_to_bed)
    pts_undist_hom = (h_bed_to_img @ pts_bed_hom.T).T
    w_denom = np.maximum(np.abs(pts_undist_hom[:, 2]), 1e-9)
    x_u = pts_undist_hom[:, 0] / w_denom
    y_u = pts_undist_hom[:, 1] / w_denom

    assert cal.camera_matrix is not None
    assert cal.dist_coeffs is not None
    fx = float(cal.camera_matrix[0, 0])
    fy = float(cal.camera_matrix[1, 1])
    cx = float(cal.camera_matrix[0, 2])
    cy = float(cal.camera_matrix[1, 2])

    xn = (x_u - cx) / fx
    yn = (y_u - cy) / fy
    r2 = xn * xn + yn * yn
    r4 = r2 * r2
    r6 = r4 * r2

    d = cal.dist_coeffs.ravel()
    k1 = float(d[0]) if len(d) > 0 else 0.0
    k2 = float(d[1]) if len(d) > 1 else 0.0
    p1 = float(d[2]) if len(d) > 2 else 0.0
    p2 = float(d[3]) if len(d) > 3 else 0.0
    k3 = float(d[4]) if len(d) > 4 else 0.0

    alpha = 1.0 + k1 * r2 + k2 * r4 + k3 * r6
    dx = 2.0 * p1 * xn * yn + p2 * (r2 + 2.0 * xn * xn)
    dy = p1 * (r2 + 2.0 * yn * yn) + 2.0 * p2 * xn * yn

    x_dist = fx * (xn * alpha + dx) + cx
    y_dist = fy * (yn * alpha + dy) + cy

    map_x = x_dist.reshape((h_px, w_px)).astype(np.float32)
    map_y = y_dist.reshape((h_px, w_px)).astype(np.float32)

    return Rectifier(
        cal=cal,
        size=size,
        map_x=map_x,
        map_y=map_y,
    )


def apply(rectifier: Rectifier, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Module-level helper to apply rectification."""
    return rectifier.apply(frame)


def rect_to_image(rectifier: Rectifier, points_px: NDArray[np.float64]) -> NDArray[np.float64]:
    """Module-level helper to transform rect px back to image frame px."""
    return rectifier.rect_to_image(points_px)


def glare_mask(
    rect_gray: NDArray[np.uint8],
    saturation_level: int = 250,
) -> NDArray[np.uint8]:
    """Compute binary mask (0 or 255) of saturated regions dilated by 3 px."""
    mask = (rect_gray >= saturation_level).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    return cv2.dilate(mask, kernel)
